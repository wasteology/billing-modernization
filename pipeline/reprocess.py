"""
Reprocess extraction after pattern deploy.

When a new pattern is deployed via the Meta Regex Helper, this module
re-runs extraction on affected rows (open review items matching the
vendor + fail_category). Rows that now extract successfully are
auto-resolved; rows that still fail get updated suggestions.
"""

import logging

import psycopg2.extras

from .database import get_connection
from .extraction_engine import ExtractionEngine
from .db_helpers import (
    write_extraction_results,
    write_gate_results,
    write_pipeline_events,
    update_review_queue,
    get_extraction_values_batch,
)
from .step_runner import STEP_PATTERN_FIELD, STEP_FIELDS

log = logging.getLogger(__name__)


def reprocess_after_fix(step: int, vendor_slug: str = None,
                        fail_category: str = None) -> dict:
    """Re-run extraction on open review rows matching criteria.

    Args:
        step: Step number (2-6)
        vendor_slug: Filter to specific vendor
        fail_category: Filter to specific fail category

    Returns:
        {total, resolved, still_failing}
    """
    conn = get_connection()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    # Find open review rows matching criteria
    sql = """
        SELECT rq.review_queue_id, rq.md5_hash, rq.step, rq.fail_category
        FROM ip_review_queue rq
        WHERE rq.step = %s AND rq.status = 'OPEN'
    """
    params = [step]

    if fail_category:
        sql += " AND rq.fail_category = %s"
        params.append(fail_category)

    cur.execute(sql, params)
    review_rows = [dict(r) for r in cur.fetchall()]

    if not review_rows:
        conn.close()
        log.info("No open review rows matching criteria for step %d", step)
        return {'total': 0, 'resolved': 0, 'still_failing': 0}

    # Get raw OCR text for these documents
    md5_list = [r['md5_hash'] for r in review_rows]
    cur.execute(
        "SELECT md5_hash, raw_ocr_text FROM ip_raw_document WHERE md5_hash = ANY(%s)",
        (md5_list,),
    )
    text_map = {row['md5_hash']: row['raw_ocr_text'] for row in cur.fetchall()}

    # Get detected vendors
    vendor_map = get_extraction_values_batch(md5_list, 'detected_vendor')

    # Reload extraction engine with fresh patterns
    engine = ExtractionEngine()
    field = STEP_PATTERN_FIELD.get(step)
    if field:
        engine.load_patterns(field=field)

    result_field = STEP_FIELDS[step][0]
    resolved = 0
    still_failing = 0

    extraction_rows = []
    gate_rows = []
    event_rows = []

    for rq_row in review_rows:
        md5 = rq_row['md5_hash']
        raw_text = text_map.get(md5, '')
        vendor = vendor_map.get(md5, vendor_slug or '')

        if vendor_slug and vendor != vendor_slug:
            continue

        if not vendor or not raw_text:
            still_failing += 1
            continue

        # Re-run extraction
        value, pattern_id = engine.extract(vendor, field, raw_text)

        if value and value != 'NO_ACCOUNT':
            # Auto-resolve: extraction now succeeds
            resolved += 1
            extraction_rows.append({
                'md5_hash': md5, 'step': step, 'field': result_field,
                'extracted_value': value, 'extraction_source': 'REPROCESS',
                'vendor_pattern_id': pattern_id,
            })
            gate_rows.append({
                'md5_hash': md5, 'step': step, 'gate_status': 'PASSED',
            })
            event_rows.append({
                'md5_hash': md5, 'step': step, 'event_type': 'REPROCESSED',
                'field': result_field, 'value': value,
                'review_queue_id': rq_row['review_queue_id'],
                'notes': f'Auto-resolved by reprocess (pattern {pattern_id})',
            })
            # Close the review row
            update_review_queue(
                rq_row['review_queue_id'], 'ACCEPT',
                corrected_value=value, resolved_by='reprocess',
                notes=f'Auto-resolved by pattern {pattern_id}', conn=conn,
            )
        elif value == 'NO_ACCOUNT':
            resolved += 1
            extraction_rows.append({
                'md5_hash': md5, 'step': step, 'field': result_field,
                'extracted_value': 'NO_ACCOUNT', 'extraction_source': 'REPROCESS',
            })
            gate_rows.append({
                'md5_hash': md5, 'step': step, 'gate_status': 'PASSED',
            })
            event_rows.append({
                'md5_hash': md5, 'step': step, 'event_type': 'REPROCESSED',
                'field': result_field, 'value': 'NO_ACCOUNT',
                'review_queue_id': rq_row['review_queue_id'],
            })
            update_review_queue(
                rq_row['review_queue_id'], 'CONFIRM_NO_ACCOUNT',
                resolved_by='reprocess', conn=conn,
            )
        else:
            still_failing += 1

    # Batch write results
    write_extraction_results(extraction_rows, conn=conn)
    write_gate_results(gate_rows, conn=conn)
    write_pipeline_events(event_rows, conn=conn)
    conn.commit()
    conn.close()

    total = resolved + still_failing
    log.info("Reprocess step %d: %d total, %d resolved, %d still failing",
             step, total, resolved, still_failing)

    print(f"\n  Reprocess Step {step}")
    print(f"  {'=' * 40}")
    print(f"    Total:          {total:>6}")
    print(f"    Resolved:       {resolved:>6}")
    print(f"    Still failing:  {still_failing:>6}")

    return {'total': total, 'resolved': resolved, 'still_failing': still_failing}
