"""
Batched PostgreSQL read/write helpers for ip_* tables.

Every write function uses psycopg2.extras.execute_values() with page_size=1000.
"""

import logging
from datetime import datetime
from typing import Optional

import psycopg2
import psycopg2.extras

from .database import get_connection

log = logging.getLogger(__name__)


# =============================================================================
# Read helpers
# =============================================================================

def fetch_raw_documents(vendor_filter: list[str] = None,
                        step: int = None,
                        needs_processing: bool = False,
                        limit: int = None) -> list[dict]:
    """Fetch documents from ip_raw_document.

    Args:
        vendor_filter: Only docs for these vendor slugs (requires step >= 2 with extraction result)
        step: If provided with needs_processing=True, only docs without a gate_result at this step
        needs_processing: If True, exclude docs that already have a gate_result at `step`
        limit: Max rows to return
    """
    conn = get_connection()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    sql = "SELECT rd.md5_hash, rd.sp_created_date, rd.source_file, rd.raw_ocr_text, rd.sync_status"
    params = []

    if vendor_filter:
        # Join to extraction_result to get detected_vendor
        sql += ", ev.extracted_value AS detected_vendor"
        sql += " FROM ip_raw_document rd"
        sql += (" LEFT JOIN ip_extraction_result ev"
                " ON rd.md5_hash = ev.md5_hash AND ev.field = 'detected_vendor'"
                " AND ev.extraction_result_id = ("
                "   SELECT MAX(extraction_result_id) FROM ip_extraction_result"
                "   WHERE md5_hash = rd.md5_hash AND field = 'detected_vendor'"
                " )")
    else:
        sql += " FROM ip_raw_document rd"

    conditions = ["rd.sync_status = 'OK'"]

    if vendor_filter:
        conditions.append("ev.extracted_value = ANY(%s)")
        params.append(vendor_filter)

    if needs_processing and step is not None:
        conditions.append(
            "NOT EXISTS ("
            "  SELECT 1 FROM ip_gate_result gr"
            "  WHERE gr.md5_hash = rd.md5_hash AND gr.step = %s"
            ")"
        )
        params.append(step)

    sql += " WHERE " + " AND ".join(conditions)
    sql += " ORDER BY rd.sp_created_date NULLS LAST"

    if limit:
        sql += " LIMIT %s"
        params.append(limit)

    cur.execute(sql, params)
    rows = cur.fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_extraction_value(md5_hash: str, field: str) -> Optional[str]:
    """Get the latest extraction value for a document + field."""
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        "SELECT extracted_value FROM ip_extraction_result"
        " WHERE md5_hash = %s AND field = %s"
        " ORDER BY extraction_result_id DESC LIMIT 1",
        (md5_hash, field),
    )
    row = cur.fetchone()
    conn.close()
    return row[0] if row else None


def get_extraction_values_batch(md5_hashes: list[str], field: str) -> dict[str, str]:
    """Get latest extraction values for a batch of documents + field."""
    if not md5_hashes:
        return {}
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        "SELECT DISTINCT ON (md5_hash) md5_hash, extracted_value"
        " FROM ip_extraction_result"
        " WHERE md5_hash = ANY(%s) AND field = %s"
        " ORDER BY md5_hash, extraction_result_id DESC",
        (md5_hashes, field),
    )
    result = {row[0]: row[1] for row in cur.fetchall()}
    conn.close()
    return result


def get_ocr_text_batch(md5_hashes: list[str]) -> dict[str, str]:
    """Fetch raw OCR text for a batch of documents."""
    if not md5_hashes:
        return {}
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        "SELECT md5_hash, raw_ocr_text FROM ip_raw_document WHERE md5_hash = ANY(%s)",
        (md5_hashes,),
    )
    result = {row[0]: row[1] for row in cur.fetchall()}
    conn.close()
    return result


def get_open_review_count(step: int) -> int:
    """Count OPEN review rows for a step."""
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        "SELECT COUNT(*) FROM ip_review_queue WHERE step = %s AND status = 'OPEN'",
        (step,),
    )
    count = cur.fetchone()[0]
    conn.close()
    return count


def get_review_queue(step: int, status: str = 'OPEN',
                     vendor: str = None, limit: int = None) -> list[dict]:
    """Fetch review queue rows for a step."""
    conn = get_connection()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    sql = "SELECT * FROM ip_review_queue WHERE step = %s AND status = %s"
    params: list = [step, status]

    if vendor:
        sql += " AND fail_category LIKE %s"
        params.append(f"%{vendor}%")

    sql += " ORDER BY opened_at"

    if limit:
        sql += " LIMIT %s"
        params.append(limit)

    cur.execute(sql, params)
    rows = cur.fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_gate_status_summary() -> dict[int, dict]:
    """Get gate status summary per step (counts of PASSED/BLOCKED/EXCLUDED + open review)."""
    conn = get_connection()
    cur = conn.cursor()

    summary = {}
    for step in range(1, 11):
        cur.execute(
            "SELECT gate_status, COUNT(*) FROM ip_gate_result"
            " WHERE step = %s GROUP BY gate_status",
            (step,),
        )
        gate_counts = dict(cur.fetchall())

        cur.execute(
            "SELECT COUNT(*) FROM ip_review_queue"
            " WHERE step = %s AND status = 'OPEN'",
            (step,),
        )
        open_review = cur.fetchone()[0]

        if gate_counts or open_review:
            summary[step] = {
                'passed': gate_counts.get('PASSED', 0),
                'blocked': gate_counts.get('BLOCKED', 0),
                'excluded': gate_counts.get('EXCLUDED', 0),
                'open_review': open_review,
            }

    conn.close()
    return summary


def get_documents_for_step(step: int, limit: int = None) -> list[dict]:
    """Fetch documents needing processing at a specific step.

    Returns docs that:
    - Have sync_status = 'OK'
    - Have passed all upstream gates (steps 1..step-1)
    - Do NOT have an EXCLUDED gate result at any upstream step
    - Do NOT already have a gate_result at this step
    """
    conn = get_connection()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    # Build upstream gate conditions
    upstream_joins = ""
    for s in range(1, step):
        upstream_joins += (
            f" JOIN ip_gate_result g{s}"
            f"   ON rd.md5_hash = g{s}.md5_hash AND g{s}.step = {s}"
            f"   AND g{s}.gate_status IN ('PASSED', 'EXCLUDED')"
        )

    sql = f"""
        SELECT rd.md5_hash, rd.sp_created_date, rd.raw_ocr_text, rd.source_file
        {upstream_joins and ', ' + ', '.join(
            f"g{s}.gate_status AS step{s}_status" for s in range(1, step)
        ) or ''}
        FROM ip_raw_document rd
        {upstream_joins}
        WHERE rd.sync_status = 'OK'
        AND NOT EXISTS (
            SELECT 1 FROM ip_gate_result gr
            WHERE gr.md5_hash = rd.md5_hash AND gr.step = %s
        )
    """
    params = [step]

    # Exclude docs with EXCLUDED upstream gate
    for s in range(1, step):
        sql += f" AND g{s}.gate_status = 'PASSED'"

    sql += " ORDER BY rd.sp_created_date NULLS LAST"

    if limit:
        sql += " LIMIT %s"
        params.append(limit)

    cur.execute(sql, params)
    rows = cur.fetchall()
    conn.close()
    return [dict(r) for r in rows]


# =============================================================================
# Write helpers — ALL batched with execute_values, page_size=1000
# =============================================================================

def write_extraction_results(rows: list[dict], conn=None) -> int:
    """Batch insert to ip_extraction_result.

    Each row: {md5_hash, step, field, extracted_value, extraction_source, vendor_pattern_id}
    """
    if not rows:
        return 0
    own_conn = conn is None
    if own_conn:
        conn = get_connection()
    cur = conn.cursor()

    sql = """
        INSERT INTO ip_extraction_result
            (md5_hash, step, field, extracted_value, extraction_source, vendor_pattern_id)
        VALUES %s
    """
    values = [
        (r['md5_hash'], r['step'], r['field'], r.get('extracted_value'),
         r.get('extraction_source', 'ENGINE'), r.get('vendor_pattern_id'))
        for r in rows
    ]
    psycopg2.extras.execute_values(cur, sql, values, page_size=1000)
    count = len(values)

    if own_conn:
        conn.commit()
        conn.close()
    return count


def write_gate_results(rows: list[dict], conn=None) -> int:
    """Batch upsert to ip_gate_result (ON CONFLICT update).

    Each row: {md5_hash, step, gate_status, last_event_id}
    """
    if not rows:
        return 0
    own_conn = conn is None
    if own_conn:
        conn = get_connection()
    cur = conn.cursor()

    sql = """
        INSERT INTO ip_gate_result (md5_hash, step, gate_status, passed_at, last_event_id)
        VALUES %s
        ON CONFLICT (md5_hash, step) DO UPDATE SET
            gate_status = EXCLUDED.gate_status,
            passed_at = EXCLUDED.passed_at,
            last_event_id = EXCLUDED.last_event_id
    """
    now = datetime.now()
    values = [
        (r['md5_hash'], r['step'], r['gate_status'],
         now if r['gate_status'] == 'PASSED' else None,
         r.get('last_event_id'))
        for r in rows
    ]
    psycopg2.extras.execute_values(cur, sql, values, page_size=1000)
    count = len(values)

    if own_conn:
        conn.commit()
        conn.close()
    return count


def write_pipeline_events(rows: list[dict], conn=None) -> list[int]:
    """Batch insert to ip_pipeline_event. Returns list of generated IDs.

    Each row: {md5_hash, step, event_type, field, value, human_actor, review_queue_id, notes}
    """
    if not rows:
        return []
    own_conn = conn is None
    if own_conn:
        conn = get_connection()
    cur = conn.cursor()

    sql = """
        INSERT INTO ip_pipeline_event
            (md5_hash, step, event_type, field, value, human_actor, review_queue_id, notes)
        VALUES %s
        RETURNING pipeline_event_id
    """
    values = [
        (r['md5_hash'], r['step'], r['event_type'], r.get('field'),
         r.get('value'), r.get('human_actor'), r.get('review_queue_id'), r.get('notes'))
        for r in rows
    ]
    psycopg2.extras.execute_values(cur, sql, values, page_size=1000, fetch=True)
    ids = [row[0] for row in cur.fetchall()]

    if own_conn:
        conn.commit()
        conn.close()
    return ids


def write_review_queue(rows: list[dict], conn=None) -> list[int]:
    """Batch insert to ip_review_queue. Returns list of generated IDs.

    Each row: {md5_hash, step, fail_category, ai_suggestion, suggestion_confidence,
               suggestion_reason, pdf_link}
    """
    if not rows:
        return []
    own_conn = conn is None
    if own_conn:
        conn = get_connection()
    cur = conn.cursor()

    sql = """
        INSERT INTO ip_review_queue
            (md5_hash, step, fail_category, ai_suggestion, suggestion_confidence,
             suggestion_reason, pdf_link, notes)
        VALUES %s
        RETURNING review_queue_id
    """
    values = [
        (r['md5_hash'], r['step'], r['fail_category'],
         r.get('ai_suggestion'), r.get('suggestion_confidence'),
         r.get('suggestion_reason'), r.get('pdf_link'), r.get('notes'))
        for r in rows
    ]
    psycopg2.extras.execute_values(cur, sql, values, page_size=1000, fetch=True)
    ids = [row[0] for row in cur.fetchall()]

    if own_conn:
        conn.commit()
        conn.close()
    return ids


def write_validation_results(rows: list[dict], conn=None) -> int:
    """Batch insert to ip_validation_result.

    Each row: {extraction_result_id, md5_hash, step, check_name, check_result, confidence, detail}
    """
    if not rows:
        return 0
    own_conn = conn is None
    if own_conn:
        conn = get_connection()
    cur = conn.cursor()

    sql = """
        INSERT INTO ip_validation_result
            (extraction_result_id, md5_hash, step, check_name, check_result, confidence, detail)
        VALUES %s
    """
    values = [
        (r['extraction_result_id'], r['md5_hash'], r['step'], r['check_name'],
         r['check_result'], r.get('confidence'), r.get('detail'))
        for r in rows
    ]
    psycopg2.extras.execute_values(cur, sql, values, page_size=1000)
    count = len(values)

    if own_conn:
        conn.commit()
        conn.close()
    return count


def write_fix_log(rows: list[dict], conn=None) -> int:
    """Batch insert to ip_fix_log.

    Each row: {step, fail_category, vendor, md5_sample, ocr_sample, fix_type, review_queue_id}
    """
    if not rows:
        return 0
    own_conn = conn is None
    if own_conn:
        conn = get_connection()
    cur = conn.cursor()

    sql = """
        INSERT INTO ip_fix_log
            (step, fail_category, vendor, md5_sample, ocr_sample, fix_type, review_queue_id)
        VALUES %s
    """
    values = [
        (r['step'], r['fail_category'], r['vendor'],
         r.get('md5_sample'), r.get('ocr_sample'),
         r.get('fix_type', 'PATTERN_FIX'), r.get('review_queue_id'))
        for r in rows
    ]
    psycopg2.extras.execute_values(cur, sql, values, page_size=1000)
    count = len(values)

    if own_conn:
        conn.commit()
        conn.close()
    return count


def update_review_queue(review_queue_id: int, disposition: str,
                        corrected_value: str = None, notes: str = None,
                        resolved_by: str = None, reroute_target: str = None,
                        conn=None):
    """Update a single review queue row with human disposition."""
    own_conn = conn is None
    if own_conn:
        conn = get_connection()
    cur = conn.cursor()

    status = 'REROUTED' if disposition == 'REROUTE' else 'RESOLVED'

    cur.execute("""
        UPDATE ip_review_queue SET
            human_action = %s,
            corrected_value = %s,
            notes = %s,
            status = %s,
            resolved_at = NOW(),
            resolved_by = %s,
            reroute_target = %s
        WHERE review_queue_id = %s
    """, (disposition, corrected_value, notes, status,
          resolved_by or 'system', reroute_target, review_queue_id))

    if own_conn:
        conn.commit()
        conn.close()


def close_review_rows(md5_hash: str, step: int, disposition: str,
                      corrected_value: str = None, conn=None) -> int:
    """Close all OPEN review rows for a document+step."""
    own_conn = conn is None
    if own_conn:
        conn = get_connection()
    cur = conn.cursor()

    status = 'REROUTED' if disposition == 'REROUTE' else 'RESOLVED'

    cur.execute("""
        UPDATE ip_review_queue SET
            human_action = %s, corrected_value = %s,
            status = %s, resolved_at = NOW(), resolved_by = 'system'
        WHERE md5_hash = %s AND step = %s AND status = 'OPEN'
    """, (disposition, corrected_value, status, md5_hash, step))
    count = cur.rowcount

    if own_conn:
        conn.commit()
        conn.close()
    return count


# =============================================================================
# Wipe helpers
# =============================================================================

def wipe_extraction_results(step: int = None, _cancel_event=None):
    """Delete extraction results (optionally for a specific step).

    Uses TRUNCATE CASCADE for full wipe (instant), DELETE for per-step.
    """
    conn = get_connection()
    cur = conn.cursor()

    if step:
        # Per-step: must use DELETE (can't truncate by condition).
        # FK-aware order: children before parents.
        #   fix_log → review_queue, vendor_pattern
        #   gate_result → pipeline_event
        #   pipeline_event → review_queue (self-ref + review FK)
        #   review_queue → raw_document
        #   validation_result → extraction_result
        #   extraction_result → vendor_pattern, raw_document
        cur.execute(
            "DELETE FROM ip_fix_log WHERE step = %s", (step,))
        cur.execute(
            "DELETE FROM ip_gate_result WHERE step = %s", (step,))
        cur.execute(
            "DELETE FROM ip_pipeline_event WHERE step = %s", (step,))
        cur.execute(
            "DELETE FROM ip_review_queue WHERE step = %s", (step,))
        cur.execute(
            "DELETE FROM ip_validation_result WHERE step = %s", (step,))
        cur.execute(
            "DELETE FROM ip_extraction_result WHERE step = %s", (step,))
    else:
        # Full wipe: TRUNCATE is instant regardless of row count
        cur.execute("""
            TRUNCATE ip_fix_log, ip_gate_result, ip_pipeline_event,
                     ip_validation_result, ip_review_queue,
                     ip_extraction_result
        """)

    conn.commit()
    log.info("Wiped extraction results%s", f" for step {step}" if step else " (all)")
    conn.close()


# =============================================================================
# Line item + catalog helpers
# =============================================================================

def write_line_items(rows: list[dict], conn=None) -> int:
    """Batch insert to ip_invoice_line_item.

    Each row: {md5_hash, invoice_date, invoice_total, vendor, account_number,
               container_index, equipment_type, equipment_size, material, schedule,
               container_id, service_id, charge_type, billed_amount, expected_amount,
               variance, variance_pct, status}
    """
    if not rows:
        return 0
    own_conn = conn is None
    if own_conn:
        conn = get_connection()
    cur = conn.cursor()

    sql = """
        INSERT INTO ip_invoice_line_item
            (md5_hash, invoice_date, invoice_total, vendor, account_number,
             container_index, equipment_type, equipment_size, material, schedule,
             container_id, service_id, charge_type, billed_amount, expected_amount,
             variance, variance_pct, status)
        VALUES %s
        ON CONFLICT (md5_hash, container_index, charge_type)
        DO UPDATE SET
            billed_amount = EXCLUDED.billed_amount,
            expected_amount = EXCLUDED.expected_amount,
            variance = EXCLUDED.variance,
            variance_pct = EXCLUDED.variance_pct,
            status = EXCLUDED.status,
            container_id = EXCLUDED.container_id,
            service_id = EXCLUDED.service_id
    """
    # Deduplicate by unique constraint key (md5_hash, container_index, charge_type)
    # keeping last occurrence. Duplicates arise from multiple charges normalizing
    # to the same charge_type within a container.
    seen = {}
    for r in rows:
        key = (r['md5_hash'], r['container_index'], r.get('charge_type'))
        seen[key] = r
    deduped = list(seen.values())

    values = [
        (r['md5_hash'], r.get('invoice_date'), r.get('invoice_total'),
         r.get('vendor'), r.get('account_number'),
         r['container_index'], r.get('equipment_type'), r.get('equipment_size'),
         r.get('material'), r.get('schedule'),
         r.get('container_id'), r.get('service_id'),
         r.get('charge_type'), r.get('billed_amount'), r.get('expected_amount'),
         r.get('variance'), r.get('variance_pct'), r['status'])
        for r in deduped
    ]
    psycopg2.extras.execute_values(cur, sql, values, page_size=1000)
    count = len(values)

    if own_conn:
        conn.commit()
        conn.close()
    return count


def write_service_catalog(rows: list[dict], conn=None) -> int:
    """Batch insert to ip_service_catalog.

    Each row: {service_id, account_number, vendor, container_id, container_index,
               equipment_type, equipment_size, material, schedule, charge_type,
               expected_rate, rate_uom, invoice_level_charge_pct, catalog_status}
    """
    if not rows:
        return 0
    own_conn = conn is None
    if own_conn:
        conn = get_connection()
    cur = conn.cursor()

    sql = """
        INSERT INTO ip_service_catalog
            (service_id, account_number, vendor, container_id, container_index,
             equipment_type, equipment_size, material, schedule, charge_type,
             expected_rate, rate_uom, invoice_level_charge_pct, catalog_status)
        VALUES %s
    """
    values = [
        (r['service_id'], r['account_number'], r['vendor'],
         r['container_id'], r['container_index'],
         r['equipment_type'], r.get('equipment_size'), r.get('material'),
         r.get('schedule'), r['charge_type'],
         r.get('expected_rate'), r.get('rate_uom'),
         r.get('invoice_level_charge_pct'),
         r.get('catalog_status', 'BUILDING'))
        for r in rows
    ]
    psycopg2.extras.execute_values(cur, sql, values, page_size=1000)
    count = len(values)

    if own_conn:
        conn.commit()
        conn.close()
    return count


def update_service_catalog(catalog_id: int, updates: dict, conn=None):
    """Update single catalog row (rate, status, etc.)."""
    if not updates:
        return
    own_conn = conn is None
    if own_conn:
        conn = get_connection()
    cur = conn.cursor()

    allowed = {'expected_rate', 'rate_uom', 'catalog_status', 'confirmed_at',
               'confirmed_by', 'invoice_level_charge_pct', 'equipment_type',
               'equipment_size', 'material', 'schedule', 'charge_type'}
    sets = []
    params = []
    for k, v in updates.items():
        if k in allowed:
            sets.append(f"{k} = %s")
            params.append(v)
    if not sets:
        if own_conn:
            conn.close()
        return

    sets.append("updated_at = NOW()")
    params.append(catalog_id)
    cur.execute(
        f"UPDATE ip_service_catalog SET {', '.join(sets)} WHERE catalog_id = %s",
        params,
    )

    if own_conn:
        conn.commit()
        conn.close()


def get_service_catalog(account_number: str, vendor: str,
                        status_filter: str = None) -> list[dict]:
    """Load catalog entries for an account+vendor combo."""
    conn = get_connection()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    sql = ("SELECT * FROM ip_service_catalog"
           " WHERE account_number = %s AND vendor = %s")
    params: list = [account_number, vendor]

    if status_filter:
        sql += " AND catalog_status = %s"
        params.append(status_filter)

    sql += " ORDER BY container_index, charge_type"
    cur.execute(sql, params)
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    return rows


def get_confirmed_catalog_accounts(vendor: str = None) -> set[tuple[str, str]]:
    """Return set of (account_number, vendor) with catalog_status=CONFIRMED."""
    conn = get_connection()
    cur = conn.cursor()

    sql = ("SELECT DISTINCT account_number, vendor FROM ip_service_catalog"
           " WHERE catalog_status = 'CONFIRMED'")
    params = []
    if vendor:
        sql += " AND vendor = %s"
        params.append(vendor)

    cur.execute(sql, params)
    result = {(r[0], r[1]) for r in cur.fetchall()}
    conn.close()
    return result


def get_line_items(md5_hash: str) -> list[dict]:
    """Fetch line items for a document."""
    conn = get_connection()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute(
        "SELECT * FROM ip_invoice_line_item WHERE md5_hash = %s"
        " ORDER BY container_index, charge_type",
        (md5_hash,),
    )
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    return rows


def wipe_line_items(md5_hashes: list[str] = None, _cancel_event=None):
    """Wipe ip_invoice_line_item (all or by hash list)."""
    conn = get_connection()
    cur = conn.cursor()

    if md5_hashes:
        cur.execute(
            "DELETE FROM ip_invoice_line_item WHERE md5_hash = ANY(%s)",
            (md5_hashes,),
        )
    else:
        cur.execute("TRUNCATE ip_invoice_line_item")

    conn.commit()
    log.info("Wiped line items%s",
             f" for {len(md5_hashes)} docs" if md5_hashes else " (all)")
    conn.close()
