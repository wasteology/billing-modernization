"""
db.py — Database access layer (5-gate HITL pipeline)
All data comes from wasteology_ops.ip_* tables (Azure PostgreSQL).

Gate structure:
  Gate 1 — OCR Quality   : ocr_score / text quality flags
  Gate 2 — Pattern Routing: vendor pattern match / NO_PATTERN
  Gate 3 — Charge Totals : CHARGE_DIFF / UNDER_CAPTURE / MISSING_BILL_TOTAL
  Gate 4 — Charge Details: field-level validation (equipment, material, schedule)
  Gate 5 — Export        : final summary + CSV download
"""
import decimal, datetime
import psycopg2, psycopg2.extras
from contextlib import contextmanager

PG_CONFIG = {
    'host':    'pg-wasteology.postgres.database.azure.com',
    'port':    5432,
    'dbname':  'wasteology_dev',
    'user':    'sstclair',
    'password':'Simple+Password+123',
    'sslmode': 'require',
}

GATE_NAMES = {
    1: 'OCR Quality',
    2: 'Pattern Routing',
    3: 'Charge Totals',
    4: 'Charge Details',
    5: 'Export',
}

# ── G1-G2 exception metadata ───────────────────────────────────────────────
TRIAGE_EXCEPTION_META = {
    'low_ocr_score': {
        'label':       'Low OCR quality',
        'description': 'OCR score below 0.6 — text may be unreliable.',
        'severity':    'error',
    },
    'no_pattern_match': {
        'label':       'No vendor pattern matched',
        'description': 'Vendor could not be identified or no extraction pattern exists.',
        'severity':    'error',
    },
}

# ── G3-G4 validation check metadata (all stored in ip_validation_result) ──
VALIDATION_CHECK_META = {
    # G3 — charge total checks
    'CHARGE_DIFF': {
        'label':       'Charge sum ≠ bill total',
        'description': 'Sum of extracted line items does not match invoice total.',
        'severity':    'error',
    },
    'UNDER_CAPTURE': {
        'label':       'Under-capture',
        'description': 'Charge sum is less than bill total — charges may be missing.',
        'severity':    'warning',
    },
    'MISSING_BILL_TOTAL': {
        'label':       'Bill total not extracted',
        'description': 'Invoice total could not be parsed from OCR text.',
        'severity':    'warning',
    },
    # G4 — per-row field checks
    'MISSING_EQUIPMENT_TYPE': {
        'label':       'Missing equipment type',
        'description': 'Charge row has no equipment_type extracted.',
        'severity':    'error',
    },
    'MISSING_MATERIAL': {
        'label':       'Missing material',
        'description': 'Charge row has no material extracted.',
        'severity':    'warning',
    },
    'RECURRING_NO_SCHEDULE': {
        'label':       'Recurring container — no schedule',
        'description': 'Front load / cart charge has no pickup schedule.',
        'severity':    'warning',
    },
    'ROLLOFF_NO_WEIGHT': {
        'label':       'Roll-off disposal — no weight',
        'description': 'Roll-off or compactor disposal charge has no weight recorded.',
        'severity':    'info',
    },
    'EQUIP_CODE_MISMATCH': {
        'label':       'Equipment/charge code mismatch',
        'description': 'Charge code is inconsistent with the equipment type.',
        'severity':    'warning',
    },
}

G3_CHECKS = {'CHARGE_DIFF', 'UNDER_CAPTURE', 'MISSING_BILL_TOTAL'}
G4_CHECKS = {'MISSING_EQUIPMENT_TYPE', 'MISSING_MATERIAL', 'RECURRING_NO_SCHEDULE',
             'ROLLOFF_NO_WEIGHT', 'EQUIP_CODE_MISMATCH'}


@contextmanager
def _conn():
    conn = psycopg2.connect(**PG_CONFIG)
    conn.autocommit = False
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def _clean(row):
    """Convert psycopg2 row → plain dict, normalising Decimal and datetime."""
    d = dict(row)
    for k, v in d.items():
        if isinstance(v, decimal.Decimal):
            d[k] = float(v)
        elif isinstance(v, (datetime.datetime, datetime.date)):
            d[k] = v.isoformat()
    return d


# ── Run lifecycle ─────────────────────────────────────────────────────────

def get_all_runs():
    with _conn() as conn:
        cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
        cur.execute("""
            SELECT run_id, created_at, doc_count, current_gate, status
            FROM wasteology_ops.ip_run ORDER BY created_at DESC LIMIT 20
        """)
        return [_clean(r) for r in cur.fetchall()]


def get_run_summary(run_id):
    with _conn() as conn:
        cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
        cur.execute("""
            SELECT r.run_id, r.created_at, r.doc_count, r.current_gate, r.status,
                   COUNT(d.run_doc_id) FILTER (WHERE d.excluded) AS excluded_count
            FROM wasteology_ops.ip_run r
            LEFT JOIN wasteology_ops.ip_run_doc d ON r.run_id = d.run_id
            WHERE r.run_id = %s
            GROUP BY r.run_id, r.created_at, r.doc_count, r.current_gate, r.status
        """, (run_id,))
        row = cur.fetchone()
        return _clean(row) if row else None


# ── Gate results ──────────────────────────────────────────────────────────

def get_gate_results(run_id, gate):
    with _conn() as conn:
        cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)

        if gate in (1, 2, 3):
            resolved_col = f'gate{gate}_resolved'
            cur.execute(f"""
                SELECT
                    rd.md5_hash AS doc_id,
                    rd.pdf_filename AS filename,
                    COALESCE(inv.vendor_name, 'Unknown') AS vendor,
                    rd.ocr_score,
                    rd.pages,
                    LENGTH(rd.raw_ocr_text) AS chars,
                    inv.status AS extract_status,
                    inv.bill_total,
                    inv.charge_sum,
                    inv.diff,
                    vpb.format_label AS pattern,
                    d.excluded,
                    d.{resolved_col} AS gate_resolved
                FROM wasteology_ops.ip_run_doc d
                JOIN wasteology_ops.ip_raw_document rd ON d.md5_hash = rd.md5_hash
                LEFT JOIN wasteology_ops.ip_invoice inv ON d.md5_hash = inv.md5_hash
                LEFT JOIN wasteology_ops.ip_vendor_pattern_bulk vpb
                    ON inv.pattern_id = vpb.pattern_id
                WHERE d.run_id = %s ORDER BY rd.pdf_filename
            """, (run_id,))
            rows = [_clean(r) for r in cur.fetchall()]

            # Annotate status
            for row in rows:
                if row.get('excluded'):
                    row['status'] = 'EXCLUDED'
                elif gate == 1:
                    score = row.get('ocr_score')
                    row['status'] = 'FLAGGED' if (score is None or score < 0.6) else 'PASS'
                elif gate == 2:
                    es = row.get('extract_status')
                    row['status'] = 'FLAGGED' if (not es or es == 'NO_PATTERN') else 'PASS'
                elif gate == 3:
                    es = row.get('extract_status')
                    bt = row.get('bill_total')
                    row['status'] = (
                        'FLAGGED' if es in ('DIFF', 'UNDER_CAPTURE') or bt is None
                        else 'PASS'
                    )
            return rows

        elif gate == 4:
            # G4 Results = all extracted charge rows
            cur.execute("""
                SELECT
                    d.md5_hash AS doc_id,
                    rd.pdf_filename AS filename,
                    COALESCE(inv.vendor_name, '') AS vendor,
                    c.service_date,
                    c.description,
                    c.charge_type,
                    c.equipment_type,
                    c.equipment_size,
                    c.material,
                    c.schedule,
                    c.charge_code,
                    c.charge_total,
                    c.weight,
                    c.weight_unit,
                    c.flag,
                    EXISTS (
                        SELECT 1 FROM wasteology_ops.ip_validation_result vr
                        WHERE vr.run_id = d.run_id AND vr.md5_hash = d.md5_hash
                          AND vr.check_name = ANY(%s) AND NOT vr.resolved
                    ) AS flagged
                FROM wasteology_ops.ip_run_doc d
                JOIN wasteology_ops.ip_raw_document rd ON d.md5_hash = rd.md5_hash
                LEFT JOIN wasteology_ops.ip_invoice inv ON d.md5_hash = inv.md5_hash
                JOIN wasteology_ops.ip_charge c ON d.md5_hash = c.md5_hash
                WHERE d.run_id = %s AND NOT d.excluded
                ORDER BY rd.pdf_filename, c.charge_idx
            """, (list(G4_CHECKS), run_id))
            return [_clean(r) for r in cur.fetchall()]

        elif gate == 5:
            cur.execute("""
                SELECT
                    rd.md5_hash AS doc_id,
                    rd.pdf_filename AS filename,
                    COALESCE(inv.vendor_name, 'Unknown') AS vendor,
                    inv.invoice_number,
                    inv.account_number,
                    inv.bill_total,
                    inv.charge_sum,
                    inv.num_charges,
                    inv.valid,
                    inv.diff,
                    inv.status AS extract_status,
                    vpb.format_label AS pattern,
                    d.excluded,
                    EXISTS (
                        SELECT 1 FROM wasteology_ops.ip_validation_result vr
                        WHERE vr.run_id = d.run_id AND vr.md5_hash = d.md5_hash
                          AND NOT vr.resolved
                    ) AS has_unresolved
                FROM wasteology_ops.ip_run_doc d
                JOIN wasteology_ops.ip_raw_document rd ON d.md5_hash = rd.md5_hash
                LEFT JOIN wasteology_ops.ip_invoice inv ON d.md5_hash = inv.md5_hash
                LEFT JOIN wasteology_ops.ip_vendor_pattern_bulk vpb
                    ON inv.pattern_id = vpb.pattern_id
                WHERE d.run_id = %s
                ORDER BY rd.pdf_filename
            """, (run_id,))
            return [_clean(r) for r in cur.fetchall()]

        return []


# ── Gate exceptions ────────────────────────────────────────────────────────

def _get_validation_exception_groups(run_id, checks):
    """Query ip_validation_result for the given check_names; return grouped exceptions."""
    with _conn() as conn:
        cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
        cur.execute("""
            SELECT vr.validation_id, vr.check_name, vr.severity, vr.detail,
                   vr.resolved, vr.variance_pct,
                   rd.pdf_filename AS filename,
                   COALESCE(inv.vendor_name, '') AS vendor,
                   d.md5_hash AS doc_id,
                   inv.diff, inv.bill_total, inv.charge_sum
            FROM wasteology_ops.ip_validation_result vr
            JOIN wasteology_ops.ip_run_doc d
                ON vr.run_id = d.run_id AND vr.md5_hash = d.md5_hash
            JOIN wasteology_ops.ip_raw_document rd ON vr.md5_hash = rd.md5_hash
            LEFT JOIN wasteology_ops.ip_invoice inv ON vr.md5_hash = inv.md5_hash
            WHERE vr.run_id = %s AND vr.check_name = ANY(%s) AND NOT d.excluded
            ORDER BY vr.check_name, rd.pdf_filename
        """, (run_id, list(checks)))
        rows = [_clean(r) for r in cur.fetchall()]

    groups = {}
    for row in rows:
        check = row.get('check_name')
        if check:
            groups.setdefault(check, []).append(row)

    out = []
    for check, findings in groups.items():
        resolved = all(f.get('resolved') for f in findings)
        meta = VALIDATION_CHECK_META.get(
            check, {'label': check, 'description': '', 'severity': 'warning'})
        out.append({
            'issue':       check,
            'label':       meta['label'],
            'description': meta['description'],
            'severity':    meta['severity'],
            'actions':     ['accept', 'queue'],
            'resolved':    resolved,
            'count':       len(findings),
            'docs': [{
                'doc_id':       f.get('doc_id'),
                'filename':     f.get('filename', ''),
                'vendor':       f.get('vendor', ''),
                'detail':       f.get('detail', ''),
                'diff':         f.get('diff'),
                'variance_pct': f.get('variance_pct'),
            } for f in findings],
        })
    return out


def get_gate_exceptions(run_id, gate):
    results = get_gate_results(run_id, gate)

    if gate == 1:
        flagged = [r for r in results if r.get('status') == 'FLAGGED']
        if not flagged:
            return []
        resolved = all(r.get('gate_resolved') for r in flagged)
        meta = TRIAGE_EXCEPTION_META['low_ocr_score']
        return [{
            'issue':       'low_ocr_score',
            'label':       meta['label'],
            'description': meta['description'],
            'severity':    meta['severity'],
            'actions':     ['accept', 'queue'],
            'resolved':    resolved,
            'count':       len(flagged),
            'docs': [{'doc_id': d['doc_id'], 'filename': d['filename'],
                      'vendor': d['vendor'], 'ocr_score': d.get('ocr_score')} for d in flagged],
        }]

    if gate == 2:
        flagged = [r for r in results if r.get('status') == 'FLAGGED']
        if not flagged:
            return []
        resolved = all(r.get('gate_resolved') for r in flagged)
        meta = TRIAGE_EXCEPTION_META['no_pattern_match']
        return [{
            'issue':       'no_pattern_match',
            'label':       meta['label'],
            'description': meta['description'],
            'severity':    meta['severity'],
            'actions':     ['accept', 'queue'],
            'resolved':    resolved,
            'count':       len(flagged),
            'docs': [{'doc_id': d['doc_id'], 'filename': d['filename'],
                      'vendor': d['vendor']} for d in flagged],
        }]

    if gate in (3, 4):
        checks = G3_CHECKS if gate == 3 else G4_CHECKS
        return _get_validation_exception_groups(run_id, checks)

    return []


# ── HITL resolve ──────────────────────────────────────────────────────────

def resolve_exception(run_id, gate, issue, doc_ids, action):
    """Resolve an exception group. Returns count resolved."""
    if gate in (3, 4):
        # G3 and G4 exceptions live in ip_validation_result
        return _resolve_validation(run_id, issue, doc_ids, action)

    # Gates 1-2: resolve via ip_run_doc.gateN_resolved
    resolved_col = f'gate{gate}_resolved'
    results = get_gate_results(run_id, gate)

    if doc_ids == 'all':
        target = [r['doc_id'] for r in results
                  if r.get('status') == 'FLAGGED' and not r.get('excluded')]
    else:
        target = list(doc_ids)

    if not target:
        return 0

    with _conn() as conn:
        cur = conn.cursor()
        for h in target:
            if action == 'queue':
                cur.execute(f"""
                    UPDATE wasteology_ops.ip_run_doc
                    SET excluded = true, {resolved_col} = true
                    WHERE run_id = %s AND md5_hash = %s
                """, (run_id, h))
            else:
                cur.execute(f"""
                    UPDATE wasteology_ops.ip_run_doc
                    SET {resolved_col} = true
                    WHERE run_id = %s AND md5_hash = %s
                """, (run_id, h))
        psycopg2.extras.execute_values(cur, """
            INSERT INTO wasteology_ops.ip_gate_event
                (run_id, md5_hash, gate, action, issue)
            VALUES %s
        """, [(run_id, h, gate, action, issue) for h in target], page_size=500)

    return len(target)


def _resolve_validation(run_id, check_name, doc_ids, action):
    with _conn() as conn:
        cur = conn.cursor()
        if doc_ids == 'all':
            cur.execute("""
                UPDATE wasteology_ops.ip_validation_result
                SET resolved = true, resolved_action = %s, resolved_at = NOW()
                WHERE run_id = %s AND check_name = %s AND NOT resolved
            """, (action, run_id, check_name))
            count = cur.rowcount
            if action == 'queue':
                cur.execute("""
                    UPDATE wasteology_ops.ip_run_doc d
                    SET excluded = true
                    FROM wasteology_ops.ip_validation_result vr
                    WHERE d.run_id = vr.run_id AND d.md5_hash = vr.md5_hash
                      AND vr.run_id = %s AND vr.check_name = %s
                """, (run_id, check_name))
        else:
            if not doc_ids:
                return 0
            # doc_ids are md5_hashes; filter by check_name to avoid cross-check resolution
            placeholders = ','.join(['%s'] * len(doc_ids))
            cur.execute(f"""
                UPDATE wasteology_ops.ip_validation_result
                SET resolved = true, resolved_action = %s, resolved_at = NOW()
                WHERE run_id = %s AND md5_hash IN ({placeholders})
                  AND check_name = %s AND NOT resolved
            """, [action, run_id] + list(doc_ids) + [check_name])
            count = cur.rowcount
            if action == 'queue':
                cur.execute(f"""
                    UPDATE wasteology_ops.ip_run_doc
                    SET excluded = true
                    WHERE run_id = %s AND md5_hash IN ({placeholders})
                """, [run_id] + list(doc_ids))
    return count


def run_validation(run_id):
    from validate_output import run_pg_validation
    return run_pg_validation(run_id, PG_CONFIG)


def push_run(run_id):
    with _conn() as conn:
        cur = conn.cursor()
        cur.execute("""
            UPDATE wasteology_ops.ip_run
            SET status = 'pushed', current_gate = 5
            WHERE run_id = %s
        """, (run_id,))


# ── Document detail ────────────────────────────────────────────────────────

def get_doc_detail(run_id, doc_id):
    with _conn() as conn:
        cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
        cur.execute("""
            SELECT
                rd.md5_hash, rd.pdf_filename AS filename, rd.pdf_path,
                rd.raw_ocr_text, rd.ocr_score, rd.pages,
                inv.vendor_name AS vendor, inv.invoice_number, inv.invoice_date,
                inv.account_number, inv.bill_total, inv.charge_sum,
                inv.num_charges, inv.valid, inv.diff, inv.status,
                vpb.format_label AS pattern,
                d.excluded
            FROM wasteology_ops.ip_run_doc d
            JOIN wasteology_ops.ip_raw_document rd ON d.md5_hash = rd.md5_hash
            LEFT JOIN wasteology_ops.ip_invoice inv ON d.md5_hash = inv.md5_hash
            LEFT JOIN wasteology_ops.ip_vendor_pattern_bulk vpb
                ON inv.pattern_id = vpb.pattern_id
            WHERE d.run_id = %s AND d.md5_hash = %s
        """, (run_id, doc_id))
        doc = cur.fetchone()
        if not doc:
            return None

        cur.execute("""
            SELECT service_date, description, charge_type, charge_total,
                   equipment_type, equipment_size, material, schedule,
                   charge_code, weight, weight_unit, flag
            FROM wasteology_ops.ip_charge
            WHERE md5_hash = %s ORDER BY charge_idx
        """, (doc_id,))
        charges = [_clean(r) for r in cur.fetchall()]

        result = _clean(doc)
        result['charges'] = charges
        return result


# ── Export ─────────────────────────────────────────────────────────────────

def get_export_rows(run_id):
    with _conn() as conn:
        cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
        cur.execute("""
            SELECT
                rd.pdf_filename,
                rd.pdf_path,
                inv.invoice_number,
                inv.invoice_date,
                inv.account_number,
                inv.bill_total,
                inv.charge_sum,
                inv.num_charges,
                inv.valid,
                inv.diff,
                c.service_date,
                c.description,
                c.charge_type,
                c.charge_total,
                c.equipment_type,
                c.equipment_size,
                c.material,
                c.schedule,
                c.charge_code,
                c.weight,
                c.weight_unit,
                c.flag
            FROM wasteology_ops.ip_run_doc d
            JOIN wasteology_ops.ip_raw_document rd ON d.md5_hash = rd.md5_hash
            JOIN wasteology_ops.ip_invoice inv ON d.md5_hash = inv.md5_hash
            JOIN wasteology_ops.ip_charge c ON d.md5_hash = c.md5_hash
            WHERE d.run_id = %s AND NOT d.excluded
            ORDER BY rd.pdf_filename, c.charge_idx
        """, (run_id,))
        return [_clean(r) for r in cur.fetchall()]


def get_run_stats(run_id):
    """Summary stats for Gate 6 / export screen."""
    with _conn() as conn:
        cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
        cur.execute("""
            SELECT
                COUNT(*) AS total_docs,
                COUNT(*) FILTER (WHERE NOT d.excluded) AS active_docs,
                COUNT(*) FILTER (WHERE d.excluded) AS excluded_docs,
                COUNT(*) FILTER (WHERE inv.status = 'VALID' AND NOT d.excluded) AS valid_docs,
                COUNT(*) FILTER (WHERE inv.status IN ('DIFF','UNDER_CAPTURE') AND NOT d.excluded) AS flagged_docs,
                SUM(inv.bill_total) FILTER (WHERE NOT d.excluded) AS total_amount,
                SUM(inv.num_charges) FILTER (WHERE NOT d.excluded) AS total_charges
            FROM wasteology_ops.ip_run_doc d
            LEFT JOIN wasteology_ops.ip_invoice inv ON d.md5_hash = inv.md5_hash
            WHERE d.run_id = %s
        """, (run_id,))
        return _clean(cur.fetchone())
