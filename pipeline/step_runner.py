"""
DB-driven step runners for the invoice processing pipeline.

Each step:
1. Calls gate_check(step)
2. Fetches documents needing processing
3. Runs extraction/validation
4. Writes results to ip_extraction_result + ip_gate_result
5. Routes failures to ip_review_queue
6. Logs events to ip_pipeline_event

Steps 1-6: OCR Validation, Vendor Detection, Account Number,
           Invoice Number, Invoice Date, Amount Due.
"""

import logging
import re
import sys
import time
from datetime import datetime

import psycopg2.extras

from .database import get_connection
from .gate_check import gate_check, GateBlockedError
from .extraction_engine import ExtractionEngine
from .ai_suggestions import get_suggestion
from .db_helpers import (
    get_documents_for_step,
    write_extraction_results,
    write_gate_results,
    write_pipeline_events,
    write_review_queue,
    write_fix_log,
    get_extraction_values_batch,
    get_open_review_count,
    wipe_extraction_results,
)

log = logging.getLogger(__name__)

_DATE_FORMATS = ('%Y-%m-%d', '%m/%d/%Y', '%m/%d/%y', '%m-%d-%Y', '%B %d, %Y', '%b %d, %Y')

def _parse_date(raw):
    """Parse extracted date string into a date object, or None if unparseable."""
    if not raw or not isinstance(raw, str):
        return None
    raw = raw.strip()
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(raw, fmt).date()
        except ValueError:
            continue
    return None


# Step field names
STEP_FIELDS = {
    1: ['ocr_status', 'document_type'],
    2: ['detected_vendor'],
    3: ['hauler_account_number'],
    4: ['hauler_invoice_number'],
    5: ['invoice_date'],
    6: ['bill_total'],
}

STEP_NAMES = {
    1: "OCR Validation",
    2: "Vendor Detection",
    3: "Account Number",
    4: "Invoice Number",
    5: "Invoice Date",
    6: "Amount Due",
    7: "Validation",
    8: "Line Item Extraction",
    9: "Catalog Match",
    10: "Charge Validation",
}

# Map step → field name used in ip_vendor_pattern
STEP_PATTERN_FIELD = {
    2: 'vendor_detection',
    3: 'account_number',
    4: 'invoice_number',
    5: 'invoice_date',
    6: 'amount_due',
}


# =============================================================================
# Non-invoice classification (ported from historical_build/processor.py)
# =============================================================================

# Layer 1 — Auto-exclude (high confidence, structurally unique)
_LAYER1_AUTO_EXCLUDE = [
    (r"CERTIFICATE OF (?:LIABILITY )?INSURANCE", "certificate_of_insurance"),
    (r"Request for Taxpayer.*Identification Number", "w9_form"),
    (r"VENDOR PROFILE\b", "vendor_profile"),
    (r"\bW-?9\b.*Internal Revenue", "w9_form"),
    (r"Form\s+W-?9\b", "w9_form"),
    (r"Ticket\s*#.*Tare.*Gross.*Net", "weigh_ticket"),
    (r"Customer\s+Service\s+Agreement.*AGREEMENT\s+NUMBER", "service_agreement"),
]
_LAYER1_RE = [
    (re.compile(p, re.IGNORECASE | re.DOTALL), label)
    for p, label in _LAYER1_AUTO_EXCLUDE
]

# Layer 2 — Suggested (needs HITL, could appear on real invoices)
_LAYER2_SUGGESTED = [
    (r"Dear\s+(?:Valued\s+)?Customer.*(?:sincerely|regards)", "letter"),
    (r"SB\s*1383.*compliance|FINAL\s+NOTICE\s+OF\s+NONCOMPLIANCE", "compliance_notice"),
    (r"proposed\s+rate\s+change.*Commission|rate\s+increase\s+notification", "rate_disclosure"),
    (r"Accounts?\s+Receivable\s+Reconciliation\s+Statement", "statement"),
    (r"Franchised\s+Service\s+Rates?\s+Effective", "rate_sheet"),
    (r"Acceptable\s+Plastic\s+Items.*Unacceptable", "recycling_mailer"),
    (r"implementing a price increase of", "price_increase_letter"),
    (r"we will be implementing a.{0,20}price increase", "price_increase_letter"),
]
_LAYER2_RE = [
    (re.compile(p, re.IGNORECASE | re.DOTALL), label)
    for p, label in _LAYER2_SUGGESTED
]

# Layer 3 — Positive invoice signals (safety net scoring)
_INVOICE_SIGNALS = [
    (re.compile(r"INVOICE\s*(?:#|NUMBER|NO\.?|DATE)", re.IGNORECASE), 3),
    (re.compile(r"(?:AMOUNT|BALANCE|TOTAL)\s*DUE", re.IGNORECASE), 2),
    (re.compile(r"(?:DUE|PAYMENT)\s*DATE", re.IGNORECASE), 2),
    (re.compile(r"REMIT\s*TO", re.IGNORECASE), 2),
]

_AUTO_EXCLUDE_CATEGORIES = frozenset({
    "certificate_of_insurance", "w9_form", "vendor_profile",
    "weigh_ticket", "service_agreement",
})

INVOICE_SIGNAL_THRESHOLD = 4
MIN_OCR_LENGTH = 50


def _classify_non_invoice(text: str) -> tuple:
    """3-layer non-invoice classification. Returns (label, confidence) or (None, None)."""
    text_for_patterns = text.replace('\\n', ' ')

    for pattern, label in _LAYER1_RE:
        if pattern.search(text_for_patterns):
            return label, "HIGH"

    for pattern, label in _LAYER2_RE:
        if pattern.search(text_for_patterns):
            invoice_score = sum(
                weight for sig_pattern, weight in _INVOICE_SIGNALS
                if sig_pattern.search(text_for_patterns)
            )
            if invoice_score >= INVOICE_SIGNAL_THRESHOLD:
                return None, None
            return label, "LOW"

    return None, None


# =============================================================================
# Step 1: OCR Validation
# =============================================================================

def run_step_1(limit: int = None, wipe: bool = False, _cancel_event=None) -> dict:
    """Step 1: OCR Validation — classify documents and flag non-invoices.

    No gate check needed (first step).
    """
    t0 = time.monotonic()
    if wipe:
        wipe_extraction_results(step=1)

    conn = get_connection()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    # Fetch documents needing step 1 processing
    sql = """
        SELECT rd.md5_hash, rd.sp_created_date, rd.raw_ocr_text
        FROM ip_raw_document rd
        WHERE rd.sync_status = 'OK'
        AND NOT EXISTS (
            SELECT 1 FROM ip_gate_result gr
            WHERE gr.md5_hash = rd.md5_hash AND gr.step = 1
        )
        ORDER BY rd.sp_created_date NULLS LAST
    """
    if limit:
        sql += f" LIMIT {limit}"
    cur.execute(sql)
    docs = cur.fetchall()
    conn.close()

    totals = {"total": 0, "valid": 0, "empty": 0, "non_invoice": 0,
              "auto_excluded": 0, "review": 0}

    extraction_rows = []
    gate_rows = []
    event_rows = []
    review_rows = []

    for doc in docs:
        if _cancel_event and _cancel_event.is_set():
            log.info("Step 1 cancelled after %d documents", totals["total"])
            break

        md5 = doc['md5_hash']
        raw_text = doc['raw_ocr_text'] or ''
        totals["total"] += 1

        text_clean = raw_text.replace('\\n', ' ').strip()

        # Check 1: Empty/short text
        if len(text_clean) < MIN_OCR_LENGTH:
            totals["empty"] += 1
            extraction_rows.append({
                'md5_hash': md5, 'step': 1, 'field': 'ocr_status',
                'extracted_value': 'INCOMPLETE_OCR', 'extraction_source': 'ENGINE',
            })
            extraction_rows.append({
                'md5_hash': md5, 'step': 1, 'field': 'document_type',
                'extracted_value': 'UNKNOWN', 'extraction_source': 'ENGINE',
            })
            review_rows.append({
                'md5_hash': md5, 'step': 1, 'fail_category': 'INCOMPLETE_OCR',
                'ai_suggestion': 'EXCLUDE',
                'suggestion_confidence': 'LOW',
                'suggestion_reason': f'OCR text length {len(text_clean)} < minimum {MIN_OCR_LENGTH}',
            })
            gate_rows.append({
                'md5_hash': md5, 'step': 1, 'gate_status': 'BLOCKED',
            })
            event_rows.append({
                'md5_hash': md5, 'step': 1, 'event_type': 'QUEUED_REVIEW',
                'field': 'ocr_status', 'value': 'INCOMPLETE_OCR',
            })
            continue

        # Check 2: Non-invoice classification (3-layer)
        non_invoice_type, confidence = _classify_non_invoice(raw_text)

        if non_invoice_type:
            totals["non_invoice"] += 1
            doc_type = 'NON_INVOICE'
            is_auto = non_invoice_type in _AUTO_EXCLUDE_CATEGORIES

            extraction_rows.append({
                'md5_hash': md5, 'step': 1, 'field': 'ocr_status',
                'extracted_value': non_invoice_type, 'extraction_source': 'ENGINE',
            })
            extraction_rows.append({
                'md5_hash': md5, 'step': 1, 'field': 'document_type',
                'extracted_value': doc_type, 'extraction_source': 'ENGINE',
            })

            if is_auto:
                # Auto-exclude: pass gate as EXCLUDED, still add to review for audit
                totals["auto_excluded"] += 1
                gate_rows.append({
                    'md5_hash': md5, 'step': 1, 'gate_status': 'EXCLUDED',
                })
                event_rows.append({
                    'md5_hash': md5, 'step': 1, 'event_type': 'EXCLUDED',
                    'field': 'ocr_status', 'value': non_invoice_type,
                    'notes': f'Auto-excluded: {non_invoice_type}',
                })
            else:
                # Suggested: route to review
                totals["review"] += 1
                review_rows.append({
                    'md5_hash': md5, 'step': 1, 'fail_category': non_invoice_type,
                    'ai_suggestion': 'EXCLUDE',
                    'suggestion_confidence': confidence,
                    'suggestion_reason': f'Non-invoice pattern: {non_invoice_type}',
                })
                gate_rows.append({
                    'md5_hash': md5, 'step': 1, 'gate_status': 'BLOCKED',
                })
                event_rows.append({
                    'md5_hash': md5, 'step': 1, 'event_type': 'QUEUED_REVIEW',
                    'field': 'ocr_status', 'value': non_invoice_type,
                })
            continue

        # Valid invoice
        totals["valid"] += 1
        extraction_rows.append({
            'md5_hash': md5, 'step': 1, 'field': 'ocr_status',
            'extracted_value': 'VALID', 'extraction_source': 'ENGINE',
        })
        extraction_rows.append({
            'md5_hash': md5, 'step': 1, 'field': 'document_type',
            'extracted_value': 'INVOICE', 'extraction_source': 'ENGINE',
        })
        gate_rows.append({
            'md5_hash': md5, 'step': 1, 'gate_status': 'PASSED',
        })
        event_rows.append({
            'md5_hash': md5, 'step': 1, 'event_type': 'GATE_PASSED',
            'field': 'ocr_status', 'value': 'VALID',
        })

        if totals["total"] % 5_000 == 0:
            log.info("  Step 1: processed %d / %d...", totals["total"], len(docs))

    # Batch write all results
    conn = get_connection()
    write_extraction_results(extraction_rows, conn=conn)
    write_gate_results(gate_rows, conn=conn)
    write_pipeline_events(event_rows, conn=conn)
    write_review_queue(review_rows, conn=conn)
    conn.commit()
    conn.close()

    elapsed = time.monotonic() - t0
    t = totals["total"]
    print(f"\n  Step 1: OCR Validation")
    print(f"  {'=' * 50}")
    print(f"    Total:           {t:>8,}")
    if t:
        print(f"    Valid:           {totals['valid']:>8,} ({totals['valid']/t*100:.1f}%)")
    print(f"    Empty/short:     {totals['empty']:>8,}")
    print(f"    Non-invoice:     {totals['non_invoice']:>8,}")
    print(f"    Auto-excluded:   {totals['auto_excluded']:>8,}")
    print(f"    Review:          {totals['review']:>8,}")
    print(f"    Time: {elapsed:.1f}s")

    return totals


# =============================================================================
# Step 2: Vendor Detection
# =============================================================================

def run_step_2(limit: int = None, wipe: bool = False, _cancel_event=None) -> dict:
    """Step 2: Detect vendor from OCR text.

    Primary: parsing_engines.vendor_detection.detect_vendor()
    Fallback: ExtractionEngine patterns from ip_vendor_pattern (field='vendor_detection')
    """
    gate_check(2)
    t0 = time.monotonic()
    if wipe:
        wipe_extraction_results(step=2)

    # Import parsing_engines vendor detection
    sys.path.insert(0, '/home/scstclair/projects/parsing_engines')
    from vendor_detection.data.vendor_detection_module_v9 import detect_vendor

    # Load DB patterns as fallback
    engine = ExtractionEngine()
    engine.load_patterns(field='vendor_detection')

    docs = get_documents_for_step(2, limit=limit)
    log.info("Step 2: %d documents to process", len(docs))

    totals = {"total": 0, "detected": 0, "engine_detected": 0, "failed": 0}

    extraction_rows = []
    gate_rows = []
    event_rows = []
    review_rows = []

    for doc in docs:
        if _cancel_event and _cancel_event.is_set():
            log.info("Step 2 cancelled after %d documents", totals["total"])
            break

        md5 = doc['md5_hash']
        raw_text = doc['raw_ocr_text'] or ''
        totals["total"] += 1

        # Primary: parsing_engines
        vendor = detect_vendor(raw_text)
        source = 'ENGINE'
        pattern_id = None

        if not vendor or vendor == "OTHER":
            # Fallback: DB patterns (iterate all vendor_detection patterns)
            for vendor_name in _get_all_vendor_slugs(engine, 'vendor_detection'):
                val, pid = engine.extract(vendor_name, 'vendor_detection', raw_text)
                if val:
                    vendor = vendor_name
                    pattern_id = pid
                    source = 'ENGINE'
                    break

        if vendor and vendor != "OTHER":
            totals["detected"] += 1
            extraction_rows.append({
                'md5_hash': md5, 'step': 2, 'field': 'detected_vendor',
                'extracted_value': vendor, 'extraction_source': source,
                'vendor_pattern_id': pattern_id,
            })
            gate_rows.append({
                'md5_hash': md5, 'step': 2, 'gate_status': 'PASSED',
            })
            event_rows.append({
                'md5_hash': md5, 'step': 2, 'event_type': 'GATE_PASSED',
                'field': 'detected_vendor', 'value': vendor,
            })
        else:
            totals["failed"] += 1
            fail_cat = 'NO_VENDOR_TEXT' if not raw_text.strip() else 'NEW_VENDOR'
            suggestion = get_suggestion(2, '', raw_text)
            review_rows.append({
                'md5_hash': md5, 'step': 2, 'fail_category': fail_cat,
                **suggestion,
            })
            gate_rows.append({
                'md5_hash': md5, 'step': 2, 'gate_status': 'BLOCKED',
            })
            event_rows.append({
                'md5_hash': md5, 'step': 2, 'event_type': 'QUEUED_REVIEW',
                'field': 'detected_vendor', 'value': fail_cat,
            })

        if totals["total"] % 5_000 == 0:
            log.info("  Step 2: processed %d / %d...", totals["total"], len(docs))

    # Batch write
    conn = get_connection()
    write_extraction_results(extraction_rows, conn=conn)
    write_gate_results(gate_rows, conn=conn)
    write_pipeline_events(event_rows, conn=conn)
    write_review_queue(review_rows, conn=conn)
    conn.commit()
    conn.close()

    elapsed = time.monotonic() - t0
    t = totals["total"]
    print(f"\n  Step 2: Vendor Detection")
    print(f"  {'=' * 50}")
    print(f"    Total:           {t:>8,}")
    if t:
        print(f"    Detected:        {totals['detected']:>8,} ({totals['detected']/t*100:.1f}%)")
    print(f"    Failed:          {totals['failed']:>8,}")
    print(f"    Time: {elapsed:.1f}s")

    return totals


def _get_all_vendor_slugs(engine: ExtractionEngine, field: str) -> list[str]:
    """Get all vendor names that have patterns for a field."""
    return list(set(
        k[0] for k in engine._cache.keys() if k[1] == field
    ))


# =============================================================================
# Steps 3-6: Generic field extraction
# =============================================================================

def _run_extraction_step(step: int, limit: int = None,
                         wipe: bool = False, _cancel_event=None) -> dict:
    """Generic extraction step for steps 3-6.

    Primary: ExtractionEngine (DB patterns from ip_vendor_pattern)
    Fallback: parsing_engines extraction functions
    """
    gate_check(step)
    t0 = time.monotonic()
    if wipe:
        wipe_extraction_results(step=step)

    field = STEP_PATTERN_FIELD[step]
    result_field = STEP_FIELDS[step][0]

    # Load DB patterns
    engine = ExtractionEngine()
    engine.load_patterns(field=field)

    # Import parsing_engines fallback
    fallback_fn = _get_fallback_function(step)

    docs = get_documents_for_step(step, limit=limit)
    log.info("Step %d: %d documents to process", step, len(docs))

    # Get detected vendors for all docs
    md5_list = [d['md5_hash'] for d in docs]
    vendor_map = get_extraction_values_batch(md5_list, 'detected_vendor')

    totals = {"total": 0, "extracted": 0, "engine_extracted": 0,
              "fallback_extracted": 0, "no_pattern": 0, "failed": 0,
              "no_account": 0}

    extraction_rows = []
    gate_rows = []
    event_rows = []
    review_rows = []

    for doc in docs:
        if _cancel_event and _cancel_event.is_set():
            log.info("Step %d cancelled after %d documents", step, totals["total"])
            break

        md5 = doc['md5_hash']
        raw_text = doc['raw_ocr_text'] or ''
        vendor = vendor_map.get(md5, '')
        totals["total"] += 1

        if not vendor:
            totals["failed"] += 1
            continue

        # Primary: ExtractionEngine (DB patterns)
        value, pattern_id = engine.extract(vendor, field, raw_text)
        source = 'ENGINE'

        if value == 'NO_ACCOUNT':
            totals["no_account"] += 1
            extraction_rows.append({
                'md5_hash': md5, 'step': step, 'field': result_field,
                'extracted_value': 'NO_ACCOUNT', 'extraction_source': source,
                'vendor_pattern_id': pattern_id,
            })
            gate_rows.append({
                'md5_hash': md5, 'step': step, 'gate_status': 'PASSED',
            })
            event_rows.append({
                'md5_hash': md5, 'step': step, 'event_type': 'GATE_PASSED',
                'field': result_field, 'value': 'NO_ACCOUNT',
                'notes': 'Vendor confirmed no account number',
            })
            continue

        # Fallback: parsing_engines
        if not value and fallback_fn:
            try:
                fb_value = fallback_fn(vendor, raw_text)
                if fb_value:
                    value = str(fb_value)
                    source = 'ENGINE'
                    pattern_id = None
                    totals["fallback_extracted"] += 1
            except Exception as e:
                log.debug("Fallback extraction error for %s step %d: %s", md5[:8], step, e)

        if value and value != 'NO_ACCOUNT':
            totals["extracted"] += 1
            if pattern_id:
                totals["engine_extracted"] += 1
            extraction_rows.append({
                'md5_hash': md5, 'step': step, 'field': result_field,
                'extracted_value': value, 'extraction_source': source,
                'vendor_pattern_id': pattern_id,
            })
            gate_rows.append({
                'md5_hash': md5, 'step': step, 'gate_status': 'PASSED',
            })
            event_rows.append({
                'md5_hash': md5, 'step': step, 'event_type': 'GATE_PASSED',
                'field': result_field, 'value': value,
            })
        else:
            totals["failed"] += 1
            patterns_exist = len(engine.get_patterns(vendor, field)) > 0
            fail_cat = 'PATTERN_FAILURE' if patterns_exist else 'NO_PATTERN'
            if step == 3:
                fail_cat = 'EXTRACTION_FAILED' if patterns_exist else 'NO_PATTERN'

            suggestion = get_suggestion(step, vendor, raw_text, md5_hash=md5)
            review_rows.append({
                'md5_hash': md5, 'step': step, 'fail_category': fail_cat,
                **suggestion,
            })
            gate_rows.append({
                'md5_hash': md5, 'step': step, 'gate_status': 'BLOCKED',
            })
            event_rows.append({
                'md5_hash': md5, 'step': step, 'event_type': 'QUEUED_REVIEW',
                'field': result_field, 'value': fail_cat,
            })

        if totals["total"] % 5_000 == 0:
            log.info("  Step %d: processed %d / %d...", step, totals["total"], len(docs))

    # Batch write
    conn = get_connection()
    write_extraction_results(extraction_rows, conn=conn)
    write_gate_results(gate_rows, conn=conn)
    write_pipeline_events(event_rows, conn=conn)
    write_review_queue(review_rows, conn=conn)
    conn.commit()
    conn.close()

    elapsed = time.monotonic() - t0
    t = totals["total"]
    print(f"\n  Step {step}: {STEP_NAMES[step]}")
    print(f"  {'=' * 50}")
    print(f"    Total:           {t:>8,}")
    if t:
        print(f"    Extracted:       {totals['extracted']:>8,} ({totals['extracted']/t*100:.1f}%)")
    if totals.get("engine_extracted"):
        print(f"    Engine:          {totals['engine_extracted']:>8,}")
    if totals.get("fallback_extracted"):
        print(f"    Fallback:        {totals['fallback_extracted']:>8,}")
    if totals.get("no_account"):
        print(f"    NO_ACCOUNT:      {totals['no_account']:>8,}")
    if totals.get("no_pattern"):
        print(f"    No pattern:      {totals['no_pattern']:>8,}")
    print(f"    Failed:          {totals['failed']:>8,}")
    print(f"    Time: {elapsed:.1f}s")

    return totals


def _get_fallback_function(step: int):
    """Import parsing_engines fallback function for a step."""
    sys.path.insert(0, '/home/scstclair/projects/parsing_engines')
    try:
        if step == 3:
            from account_number.account_extraction_engine import extract_account
            return extract_account
        elif step == 4:
            from invoice_number.invoice_extraction_engine import extract_invoice_number
            return extract_invoice_number
        elif step == 5:
            from dates.date_extraction_engine import extract_invoice_date
            return extract_invoice_date
        elif step == 6:
            from amount_due.amount_due_extraction_engine import extract_bill_total
            return extract_bill_total
    except ImportError as e:
        log.warning("Could not import parsing_engines fallback for step %d: %s", step, e)
    return None


# Public step runner functions
def run_step_3(limit: int = None, wipe: bool = False, _cancel_event=None) -> dict:
    """Step 3: Account Number Extraction."""
    return _run_extraction_step(3, limit=limit, wipe=wipe, _cancel_event=_cancel_event)


def run_step_4(limit: int = None, wipe: bool = False, _cancel_event=None) -> dict:
    """Step 4: Invoice Number Extraction."""
    return _run_extraction_step(4, limit=limit, wipe=wipe, _cancel_event=_cancel_event)


def run_step_5(limit: int = None, wipe: bool = False, _cancel_event=None) -> dict:
    """Step 5: Invoice Date Extraction."""
    return _run_extraction_step(5, limit=limit, wipe=wipe, _cancel_event=_cancel_event)


def run_step_6(limit: int = None, wipe: bool = False, _cancel_event=None) -> dict:
    """Step 6: Amount Due Extraction."""
    return _run_extraction_step(6, limit=limit, wipe=wipe, _cancel_event=_cancel_event)


# =============================================================================
# Step 8: Line Item Extraction
# =============================================================================

def _import_charge_engines():
    """Import parsing_engines charge extraction and normalization functions."""
    sys.path.insert(0, '/home/scstclair/projects/parsing_engines')
    from charge_code.unified import extract_all_charges
    from line_items.line_item_extraction_module import extract_line_item_fields
    from line_items.weight_extraction_module import extract_weight
    from charge_code_normalization.charge_code_normalization_engine import normalize_charge
    return extract_all_charges, extract_line_item_fields, extract_weight, normalize_charge


def run_step_8(limit: int = None, wipe: bool = False, _cancel_event=None) -> dict:
    """Step 8: Line Item Extraction — extract per-charge detail from OCR text.

    Path A (no confirmed catalog): extract charges, route all to review.
    Path B (confirmed catalog): match against expected charges, auto-pass matches.
    """
    gate_check(8)
    t0 = time.monotonic()

    from .db_helpers import (
        get_confirmed_catalog_accounts, get_service_catalog,
        write_line_items, wipe_line_items,
        get_ocr_text_batch,
    )

    if wipe:
        wipe_line_items()
        wipe_extraction_results(step=8)

    # Load DB-driven charge patterns
    engine = ExtractionEngine()
    engine.load_patterns(field='charge_line_item')

    # Import parsing engines (fallback + normalization)
    extract_all_charges, extract_line_item_fields, extract_weight, normalize_charge = \
        _import_charge_engines()

    # Fetch documents needing step 8 processing (passed steps 1-7)
    docs = get_documents_for_step(8, limit=limit)
    log.info("Step 8: %d documents to process", len(docs))

    if not docs:
        print(f"\n  Step 8: Line Item Extraction — 0 documents to process")
        return {'total': 0, 'path_a': 0, 'path_b': 0,
                'charges_extracted': 0, 'review_queued': 0, 'elapsed': 0}

    # Pre-load header extraction results
    md5_list = [d['md5_hash'] for d in docs]
    vendor_map = get_extraction_values_batch(md5_list, 'detected_vendor')
    account_map = get_extraction_values_batch(md5_list, 'hauler_account_number')
    date_map = get_extraction_values_batch(md5_list, 'invoice_date')
    amount_map = get_extraction_values_batch(md5_list, 'bill_total')

    # Pre-load confirmed catalog accounts
    confirmed_accounts = get_confirmed_catalog_accounts()

    totals = {'total': 0, 'path_a': 0, 'path_b': 0,
              'charges_extracted': 0, 'engine_extracted': 0,
              'fallback_extracted': 0, 'review_queued': 0}

    line_item_rows = []
    gate_rows = []
    event_rows = []
    review_rows = []

    for doc in docs:
        if _cancel_event and _cancel_event.is_set():
            log.info("Step 8 cancelled after %d documents", totals['total'])
            break

        md5 = doc['md5_hash']
        raw_text = doc['raw_ocr_text'] or ''
        vendor = vendor_map.get(md5, '')
        account = account_map.get(md5, '')
        inv_date = _parse_date(date_map.get(md5))
        try:
            bill_total = float(amount_map[md5]) if md5 in amount_map else None
        except (ValueError, TypeError):
            bill_total = None
        totals['total'] += 1

        if not vendor:
            continue

        # Determine path
        is_path_b = (account, vendor) in confirmed_accounts

        # Primary: DB-driven extraction via ExtractionEngine
        engine_charges = engine.extract_charges(vendor, raw_text)
        charges = []
        used_engine = False

        if engine_charges:
            # Convert engine dicts to ChargeItem-like objects for downstream
            for ec in engine_charges:
                charges.append(type('ChargeItem', (), {
                    'charge_description': ec.get('charge_description'),
                    'amount': ec.get('amount'),
                    'qty': ec.get('qty'),
                    'unit_price': ec.get('unit_price'),
                })())
            used_engine = True
            totals['engine_extracted'] += 1

        # Fallback: parsing_engines (bridge during migration)
        if not charges:
            try:
                charges = extract_all_charges(vendor, raw_text)
                if charges:
                    totals['fallback_extracted'] += 1
            except Exception as e:
                log.debug("Charge extraction error for %s: %s", md5[:8], e)
                charges = []

        if not charges:
            # No charges extracted — route to review
            review_rows.append({
                'md5_hash': md5, 'step': 8,
                'fail_category': 'NO_CHARGES_EXTRACTED',
                'ai_suggestion': None,
                'suggestion_confidence': None,
                'suggestion_reason': f'extract_all_charges returned empty for {vendor}',
            })
            gate_rows.append({'md5_hash': md5, 'step': 8, 'gate_status': 'BLOCKED'})
            event_rows.append({
                'md5_hash': md5, 'step': 8, 'event_type': 'QUEUED_REVIEW',
                'field': 'line_items', 'value': 'NO_CHARGES_EXTRACTED',
            })
            totals['review_queued'] += 1
            continue

        # Build line items from extracted charges
        container_idx = 0
        invoice_level_items = []
        container_items = []

        for charge in charges:
            desc = charge.charge_description or ''
            amount = charge.amount

            # Normalize charge type
            norm = None
            try:
                norm = normalize_charge(vendor, desc)
            except Exception:
                pass
            charge_type = norm.charge_code if norm else desc[:100]
            classification = norm.classification if norm else None

            # Check if invoice-level charge (fuel surcharge, admin fee, etc.)
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

            # Container-level charge
            container_idx += 1

            # Extract line item fields
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

        # Deduplicate by (md5_hash, container_index, charge_type) —
        # the unique index requires no two rows share the same key in one batch.
        # When duplicates exist (e.g., two "Fuel Surcharge" at container_index=0),
        # merge by summing billed_amount.
        seen_keys: dict[tuple, int] = {}
        deduped_items = []
        for item in all_items:
            key = (item['md5_hash'], item['container_index'], item['charge_type'])
            if key in seen_keys:
                idx = seen_keys[key]
                existing = deduped_items[idx]
                # Sum amounts
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

        if is_path_b:
            # Path B: match against catalog in Step 9
            totals['path_b'] += 1
            gate_rows.append({'md5_hash': md5, 'step': 8, 'gate_status': 'PASSED'})
            event_rows.append({
                'md5_hash': md5, 'step': 8, 'event_type': 'GATE_PASSED',
                'field': 'line_items',
                'value': f'{len(all_items)} charges (Path B)',
            })
        else:
            # Path A: route to review for HITL
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

        if totals['total'] % 5_000 == 0:
            log.info("  Step 8: processed %d / %d...", totals['total'], len(docs))

    # Batch write
    conn = get_connection()
    if line_item_rows:
        write_line_items(line_item_rows, conn=conn)
    write_gate_results(gate_rows, conn=conn)
    write_pipeline_events(event_rows, conn=conn)
    if review_rows:
        write_review_queue(review_rows, conn=conn)
    conn.commit()
    conn.close()

    elapsed = time.monotonic() - t0
    t = totals['total']
    print(f"\n  Step 8: Line Item Extraction")
    print(f"  {'=' * 50}")
    print(f"    Total:             {t:>8,}")
    if t:
        print(f"    Path A (review):   {totals['path_a']:>8,} ({totals['path_a']/t*100:.1f}%)")
        print(f"    Path B (catalog):  {totals['path_b']:>8,} ({totals['path_b']/t*100:.1f}%)")
    print(f"    Charges extracted: {totals['charges_extracted']:>8,}")
    if totals.get('engine_extracted'):
        print(f"    Engine (DB):       {totals['engine_extracted']:>8,}")
    if totals.get('fallback_extracted'):
        print(f"    Fallback (PE):     {totals['fallback_extracted']:>8,}")
    print(f"    Review queued:     {totals['review_queued']:>8,}")
    print(f"    Time: {elapsed:.1f}s")

    totals['elapsed'] = round(elapsed, 1)
    return totals


# =============================================================================
# Step 9: Catalog Match
# =============================================================================

def run_step_9(limit: int = None, wipe: bool = False, _cancel_event=None) -> dict:
    """Step 9: Catalog Match — match extracted line items against ip_service_catalog.

    For each document's line items, match equipment_type + equipment_size + material
    against catalog entries. Set container_id + service_id on match.
    """
    gate_check(9)
    t0 = time.monotonic()

    from .db_helpers import (
        get_service_catalog, write_line_items,
    )

    if wipe:
        wipe_extraction_results(step=9)

    conn = get_connection()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    # Fetch documents: have step 8 PASSED gate, no step 9 gate yet
    cur.execute("""
        SELECT DISTINCT li.md5_hash, li.vendor, li.account_number
        FROM ip_invoice_line_item li
        JOIN ip_gate_result g8 ON li.md5_hash = g8.md5_hash
            AND g8.step = 8 AND g8.gate_status = 'PASSED'
        WHERE NOT EXISTS (
            SELECT 1 FROM ip_gate_result g9
            WHERE g9.md5_hash = li.md5_hash AND g9.step = 9
        )
        AND li.status = 'PENDING'
    """)
    doc_rows = cur.fetchall()
    conn.close()

    if limit:
        doc_rows = doc_rows[:limit]

    log.info("Step 9: %d documents to process", len(doc_rows))

    if not doc_rows:
        print(f"\n  Step 9: Catalog Match — 0 documents to process")
        return {'total': 0, 'matched': 0, 'unmatched': 0,
                'review_queued': 0, 'elapsed': 0}

    # Pre-load catalogs per (account, vendor)
    catalog_cache = {}

    totals = {'total': 0, 'matched': 0, 'unmatched': 0, 'review_queued': 0}

    update_rows = []
    gate_rows = []
    event_rows = []
    review_rows = []

    for doc_row in doc_rows:
        if _cancel_event and _cancel_event.is_set():
            log.info("Step 9 cancelled after %d documents", totals['total'])
            break

        md5 = doc_row['md5_hash']
        vendor = doc_row['vendor'] or ''
        account = doc_row['account_number'] or ''
        totals['total'] += 1

        # Load catalog for this account+vendor
        cache_key = (account, vendor)
        if cache_key not in catalog_cache:
            catalog_cache[cache_key] = get_service_catalog(account, vendor)
        catalog = catalog_cache[cache_key]

        if not catalog:
            # No catalog entries — everything is unmatched
            gate_rows.append({'md5_hash': md5, 'step': 9, 'gate_status': 'PASSED'})
            event_rows.append({
                'md5_hash': md5, 'step': 9, 'event_type': 'GATE_PASSED',
                'field': 'catalog_match', 'value': 'No catalog — skip match',
            })
            continue

        # Load line items for this doc
        conn2 = get_connection()
        cur2 = conn2.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur2.execute(
            "SELECT * FROM ip_invoice_line_item WHERE md5_hash = %s AND status = 'PENDING'"
            " ORDER BY container_index",
            (md5,),
        )
        items = [dict(r) for r in cur2.fetchall()]
        conn2.close()

        doc_has_unmatched = False

        for item in items:
            if item['container_index'] == 0:
                # Invoice-level charges — skip catalog match
                continue

            eq_type = (item.get('equipment_type') or '').upper().strip()
            eq_size = (item.get('equipment_size') or '').upper().strip()
            material = (item.get('material') or '').upper().strip()

            # Exact match: equipment_type + equipment_size + material
            matched_entry = None
            for cat in catalog:
                c_type = (cat.get('equipment_type') or '').upper().strip()
                c_size = (cat.get('equipment_size') or '').upper().strip()
                c_mat = (cat.get('material') or '').upper().strip()
                c_charge = (cat.get('charge_type') or '').upper().strip()
                i_charge = (item.get('charge_type') or '').upper().strip()

                if c_type == eq_type and c_size == eq_size and c_mat == material:
                    matched_entry = cat
                    break

            # Fuzzy fallback: equipment_type + equipment_size only
            if not matched_entry:
                fuzzy_matches = [
                    cat for cat in catalog
                    if (cat.get('equipment_type') or '').upper().strip() == eq_type
                    and (cat.get('equipment_size') or '').upper().strip() == eq_size
                ]
                if len(fuzzy_matches) == 1:
                    matched_entry = fuzzy_matches[0]

            if matched_entry:
                totals['matched'] += 1
                update_rows.append({
                    'md5_hash': md5,
                    'invoice_date': item.get('invoice_date'),
                    'invoice_total': item.get('invoice_total'),
                    'vendor': vendor, 'account_number': account,
                    'container_index': item['container_index'],
                    'equipment_type': item.get('equipment_type'),
                    'equipment_size': item.get('equipment_size'),
                    'material': item.get('material'),
                    'schedule': matched_entry.get('schedule'),
                    'container_id': matched_entry.get('container_id'),
                    'service_id': matched_entry.get('service_id'),
                    'charge_type': item.get('charge_type'),
                    'billed_amount': item.get('billed_amount'),
                    'expected_amount': matched_entry.get('expected_rate'),
                    'variance': None, 'variance_pct': None,
                    'status': 'PENDING',
                })
            else:
                totals['unmatched'] += 1
                doc_has_unmatched = True

        if doc_has_unmatched:
            totals['review_queued'] += 1
            review_rows.append({
                'md5_hash': md5, 'step': 9,
                'fail_category': 'UNMATCHED_CONTAINER',
                'ai_suggestion': None,
                'suggestion_confidence': None,
                'suggestion_reason': f'One or more containers not matched in catalog for {vendor} / {account}',
            })
            gate_rows.append({'md5_hash': md5, 'step': 9, 'gate_status': 'BLOCKED'})
            event_rows.append({
                'md5_hash': md5, 'step': 9, 'event_type': 'QUEUED_REVIEW',
                'field': 'catalog_match', 'value': 'UNMATCHED_CONTAINER',
            })
        else:
            gate_rows.append({'md5_hash': md5, 'step': 9, 'gate_status': 'PASSED'})
            event_rows.append({
                'md5_hash': md5, 'step': 9, 'event_type': 'GATE_PASSED',
                'field': 'catalog_match', 'value': 'All containers matched',
            })

        if totals['total'] % 5_000 == 0:
            log.info("  Step 9: processed %d / %d...", totals['total'], len(doc_rows))

    # Batch write
    conn = get_connection()
    if update_rows:
        write_line_items(update_rows, conn=conn)
    write_gate_results(gate_rows, conn=conn)
    write_pipeline_events(event_rows, conn=conn)
    if review_rows:
        write_review_queue(review_rows, conn=conn)
    conn.commit()
    conn.close()

    elapsed = time.monotonic() - t0
    t = totals['total']
    print(f"\n  Step 9: Catalog Match")
    print(f"  {'=' * 50}")
    print(f"    Total:           {t:>8,}")
    if t:
        print(f"    Matched:         {totals['matched']:>8,}")
        print(f"    Unmatched:       {totals['unmatched']:>8,}")
    print(f"    Review queued:   {totals['review_queued']:>8,}")
    print(f"    Time: {elapsed:.1f}s")

    totals['elapsed'] = round(elapsed, 1)
    return totals


# =============================================================================
# Step 10: Charge Validation
# =============================================================================

def run_step_10(limit: int = None, wipe: bool = False, _cancel_event=None) -> dict:
    """Step 10: Charge Validation — compare billed vs expected amounts.

    Sets variance, variance_pct, and final status on each line item.
    """
    gate_check(10)
    t0 = time.monotonic()

    from .db_helpers import (
        get_service_catalog, write_line_items,
    )
    from decimal import Decimal, ROUND_HALF_UP

    if wipe:
        wipe_extraction_results(step=10)

    conn = get_connection()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    # Fetch documents: passed step 9, no step 10 gate yet
    cur.execute("""
        SELECT DISTINCT li.md5_hash, li.vendor, li.account_number
        FROM ip_invoice_line_item li
        JOIN ip_gate_result g9 ON li.md5_hash = g9.md5_hash
            AND g9.step = 9 AND g9.gate_status = 'PASSED'
        WHERE NOT EXISTS (
            SELECT 1 FROM ip_gate_result g10
            WHERE g10.md5_hash = li.md5_hash AND g10.step = 10
        )
        AND li.status IN ('PENDING', 'MATCH')
    """)
    doc_rows = cur.fetchall()

    if limit:
        doc_rows = doc_rows[:limit]
    conn.close()

    log.info("Step 10: %d documents to process", len(doc_rows))

    if not doc_rows:
        print(f"\n  Step 10: Charge Validation — 0 documents to process")
        return {'total': 0, 'match': 0, 'rate_variance': 0,
                'unexpected': 0, 'missing': 0, 'invoice_level': 0, 'elapsed': 0}

    # Pre-load catalogs
    catalog_cache = {}

    totals = {'total': 0, 'match': 0, 'rate_variance': 0,
              'unexpected': 0, 'missing': 0, 'invoice_level': 0}

    update_rows = []
    gate_rows = []
    event_rows = []
    review_rows = []

    for doc_row in doc_rows:
        if _cancel_event and _cancel_event.is_set():
            log.info("Step 10 cancelled after %d documents", totals['total'])
            break

        md5 = doc_row['md5_hash']
        vendor = doc_row['vendor'] or ''
        account = doc_row['account_number'] or ''
        totals['total'] += 1

        # Load line items for this doc
        conn2 = get_connection()
        cur2 = conn2.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur2.execute(
            "SELECT * FROM ip_invoice_line_item WHERE md5_hash = %s"
            " AND status IN ('PENDING', 'MATCH')"
            " ORDER BY container_index",
            (md5,),
        )
        items = [dict(r) for r in cur2.fetchall()]
        conn2.close()

        # Load catalog
        cache_key = (account, vendor)
        if cache_key not in catalog_cache:
            catalog_cache[cache_key] = get_service_catalog(account, vendor)
        catalog = catalog_cache[cache_key]

        doc_has_variance = False

        # Build set of expected charges from catalog for missing-charge detection
        expected_charges = set()
        for cat in catalog:
            cid = cat.get('container_id')
            ct = cat.get('charge_type')
            if cid and ct:
                expected_charges.add((cid, ct))

        seen_charges = set()

        for item in items:
            billed = item.get('billed_amount')
            expected = item.get('expected_amount')

            # Track what we've seen
            if item.get('container_id') and item.get('charge_type'):
                seen_charges.add((item['container_id'], item['charge_type']))

            # Invoice-level charges (container_index=0): check against catalog pct
            if item['container_index'] == 0:
                # Validate fuel surcharge / admin fee percentage
                inv_total_str = item.get('invoice_total')
                if inv_total_str and billed:
                    try:
                        inv_total = float(inv_total_str)
                        billed_f = float(billed)
                        if inv_total > 0:
                            pct = billed_f / inv_total
                            # Find matching catalog entry for invoice-level charge
                            cat_pct = None
                            for cat in catalog:
                                if cat.get('invoice_level_charge_pct') is not None:
                                    cat_pct = float(cat['invoice_level_charge_pct'])
                                    break
                            if cat_pct is not None:
                                diff = abs(pct - cat_pct)
                                status = 'MATCH' if diff < 0.005 else 'INVOICE_LEVEL_VARIANCE'
                            else:
                                status = 'PENDING'
                        else:
                            status = 'PENDING'
                    except (ValueError, TypeError):
                        status = 'PENDING'
                else:
                    status = 'PENDING'

                if status == 'INVOICE_LEVEL_VARIANCE':
                    totals['invoice_level'] += 1
                    doc_has_variance = True

                update_rows.append({
                    **item,
                    'status': status,
                })
                continue

            # Container-level charges: compare billed vs expected
            if billed is not None and expected is not None:
                try:
                    billed_d = Decimal(str(billed))
                    expected_d = Decimal(str(expected))
                    variance = billed_d - expected_d
                    if expected_d != 0:
                        variance_pct = (variance / expected_d * 100).quantize(
                            Decimal('0.01'), rounding=ROUND_HALF_UP)
                    else:
                        variance_pct = None

                    if variance == 0:
                        status = 'MATCH'
                        totals['match'] += 1
                    else:
                        status = 'RATE_VARIANCE'
                        totals['rate_variance'] += 1
                        doc_has_variance = True

                    update_rows.append({
                        **item,
                        'variance': float(variance),
                        'variance_pct': float(variance_pct) if variance_pct is not None else None,
                        'status': status,
                    })
                except (ValueError, TypeError):
                    update_rows.append({**item, 'status': 'PENDING'})
            elif expected is None and item.get('container_id'):
                # Charge exists on invoice but not in catalog for this container
                totals['unexpected'] += 1
                doc_has_variance = True
                update_rows.append({**item, 'status': 'UNEXPECTED_CHARGE'})
            else:
                # No expected amount (no catalog match) — leave as-is
                update_rows.append({**item, 'status': 'MATCH'})
                totals['match'] += 1

        # Check for missing charges (in catalog but not on invoice)
        missing = expected_charges - seen_charges
        for container_id, charge_type in missing:
            cat_entry = next(
                (c for c in catalog
                 if c.get('container_id') == container_id
                 and c.get('charge_type') == charge_type),
                None,
            )
            if cat_entry:
                totals['missing'] += 1
                doc_has_variance = True
                update_rows.append({
                    'md5_hash': md5,
                    'invoice_date': items[0].get('invoice_date') if items else None,
                    'invoice_total': items[0].get('invoice_total') if items else None,
                    'vendor': vendor, 'account_number': account,
                    'container_index': cat_entry.get('container_index', 0),
                    'equipment_type': cat_entry.get('equipment_type'),
                    'equipment_size': cat_entry.get('equipment_size'),
                    'material': cat_entry.get('material'),
                    'schedule': cat_entry.get('schedule'),
                    'container_id': container_id,
                    'service_id': cat_entry.get('service_id'),
                    'charge_type': charge_type,
                    'billed_amount': None,
                    'expected_amount': cat_entry.get('expected_rate'),
                    'variance': None, 'variance_pct': None,
                    'status': 'MISSING_CHARGE',
                })

        if doc_has_variance:
            review_rows.append({
                'md5_hash': md5, 'step': 10,
                'fail_category': 'CHARGE_VARIANCE',
                'ai_suggestion': None,
                'suggestion_confidence': None,
                'suggestion_reason': f'Rate variance or unexpected/missing charges for {vendor} / {account}',
            })
            gate_rows.append({'md5_hash': md5, 'step': 10, 'gate_status': 'BLOCKED'})
            event_rows.append({
                'md5_hash': md5, 'step': 10, 'event_type': 'QUEUED_REVIEW',
                'field': 'charge_validation', 'value': 'CHARGE_VARIANCE',
            })
        else:
            gate_rows.append({'md5_hash': md5, 'step': 10, 'gate_status': 'PASSED'})
            event_rows.append({
                'md5_hash': md5, 'step': 10, 'event_type': 'GATE_PASSED',
                'field': 'charge_validation', 'value': 'All charges validated',
            })

        if totals['total'] % 5_000 == 0:
            log.info("  Step 10: processed %d / %d...", totals['total'], len(doc_rows))

    # Batch write
    conn = get_connection()
    if update_rows:
        write_line_items(update_rows, conn=conn)
    write_gate_results(gate_rows, conn=conn)
    write_pipeline_events(event_rows, conn=conn)
    if review_rows:
        write_review_queue(review_rows, conn=conn)
    conn.commit()
    conn.close()

    elapsed = time.monotonic() - t0
    t = totals['total']
    print(f"\n  Step 10: Charge Validation")
    print(f"  {'=' * 50}")
    print(f"    Total:             {t:>8,}")
    if t:
        print(f"    Match:             {totals['match']:>8,}")
        print(f"    Rate variance:     {totals['rate_variance']:>8,}")
        print(f"    Unexpected:        {totals['unexpected']:>8,}")
        print(f"    Missing:           {totals['missing']:>8,}")
        print(f"    Invoice-level:     {totals['invoice_level']:>8,}")
    print(f"    Time: {elapsed:.1f}s")

    totals['elapsed'] = round(elapsed, 1)
    return totals


# =============================================================================
# Validation — post-extraction quality gate
# =============================================================================

def run_validation(wipe: bool = False, _cancel_event=None) -> dict:
    """Run validation checks on all extracted values (post-extraction, pre-staging).

    Batch-optimized: pre-loads vendor profiles, extraction results, and collision
    data into memory, then runs all checks in Python with zero per-doc DB queries.

    Returns summary: {total, checked, passed, failed, failures_by_check, failures_by_vendor}
    """
    from .validators import (
        run_validation as _run_checks, all_checks_pass,
        load_all_vendor_profiles,
    )
    from .db_helpers import write_validation_results, write_review_queue, write_gate_results

    conn = get_connection()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    if wipe:
        cur.execute("TRUNCATE ip_validation_result")
        cur.execute("DELETE FROM ip_review_queue WHERE step = 7")
        cur.execute("DELETE FROM ip_gate_result WHERE step = 7")
        conn.commit()
        log.info("Wiped ip_validation_result + step-7 review queue + step-7 gates")

    # Fields to validate per step
    step_fields = {
        3: 'hauler_account_number',
        4: 'hauler_invoice_number',
        5: 'invoice_date',
        6: 'bill_total',
    }

    t0 = time.time()

    # === BATCH LOAD 1: Vendor profiles (16 rows) ===
    profiles_cache = load_all_vendor_profiles(conn=conn)

    # === BATCH LOAD 2: All docs that passed all 6 gates ===
    cur.execute("""
        SELECT DISTINCT r.md5_hash, r.raw_ocr_text,
               ev.extracted_value AS vendor
        FROM ip_raw_document r
        JOIN ip_gate_result g1 ON r.md5_hash = g1.md5_hash AND g1.step = 1 AND g1.gate_status = 'PASSED'
        JOIN ip_gate_result g2 ON r.md5_hash = g2.md5_hash AND g2.step = 2 AND g2.gate_status = 'PASSED'
        JOIN ip_gate_result g3 ON r.md5_hash = g3.md5_hash AND g3.step = 3 AND g3.gate_status IN ('PASSED', 'EXCLUDED')
        JOIN ip_gate_result g4 ON r.md5_hash = g4.md5_hash AND g4.step = 4 AND g4.gate_status IN ('PASSED', 'EXCLUDED')
        JOIN ip_gate_result g5 ON r.md5_hash = g5.md5_hash AND g5.step = 5 AND g5.gate_status IN ('PASSED', 'EXCLUDED')
        JOIN ip_gate_result g6 ON r.md5_hash = g6.md5_hash AND g6.step = 6 AND g6.gate_status IN ('PASSED', 'EXCLUDED')
        LEFT JOIN ip_extraction_result ev ON r.md5_hash = ev.md5_hash AND ev.field = 'detected_vendor'
    """)
    docs = cur.fetchall()
    total = len(docs)
    log.info("Validation: %d documents passed all gates (%.1fs)", total, time.time() - t0)

    # Skip docs that already have validation results (unless wiped)
    if not wipe:
        cur.execute("SELECT DISTINCT md5_hash FROM ip_validation_result")
        already_validated = {r['md5_hash'] for r in cur.fetchall()}
        docs = [d for d in docs if d['md5_hash'] not in already_validated]
        log.info("Validation: %d new documents to validate (%d already done)",
                 len(docs), total - len(docs))

    if not docs:
        conn.close()
        return {'total': total, 'checked': 0, 'passed': 0, 'failed': 0,
                'pass_rate': 'N/A', 'failures_by_check': {}, 'failures_by_vendor': {},
                'elapsed': f'{time.time() - t0:.1f}s'}

    doc_md5s = [d['md5_hash'] for d in docs]
    doc_map = {d['md5_hash']: d for d in docs}

    # === BATCH LOAD 3: All extraction results for fields 3-6 in one query ===
    # Use a temp approach: load all extraction results for the target md5s
    # Process in chunks to avoid oversized IN clauses
    extraction_map = {}  # (md5_hash, field) -> {extraction_result_id, extracted_value}
    CHUNK = 10000
    for i in range(0, len(doc_md5s), CHUNK):
        chunk = doc_md5s[i:i + CHUNK]
        cur.execute("""
            SELECT DISTINCT ON (md5_hash, field)
                md5_hash, field, extraction_result_id, extracted_value
            FROM ip_extraction_result
            WHERE md5_hash = ANY(%s)
              AND field = ANY(%s)
            ORDER BY md5_hash, field, extraction_result_id DESC
        """, (chunk, list(step_fields.values())))
        for row in cur.fetchall():
            if row['extracted_value']:
                extraction_map[(row['md5_hash'], row['field'])] = {
                    'extraction_result_id': row['extraction_result_id'],
                    'extracted_value': row['extracted_value'],
                }
    log.info("Validation: loaded %d extraction results (%.1fs)",
             len(extraction_map), time.time() - t0)

    # === PROCESS: All checks run in Python, zero DB queries per doc ===
    checked = 0
    passed = 0
    failed = 0
    failures_by_check = {}
    failures_by_vendor = {}
    all_results = []
    review_rows = []
    gate_rows = []

    for i, md5 in enumerate(doc_md5s):
        if _cancel_event and _cancel_event.is_set():
            log.info("Validation cancelled at %d/%d", i, len(doc_md5s))
            break

        doc = doc_map[md5]
        vendor = doc['vendor'] or ''
        raw_text = doc['raw_ocr_text'] or ''
        doc_failures = []

        for step, field in step_fields.items():
            er = extraction_map.get((md5, field))
            if not er:
                continue

            results = _run_checks(
                md5_hash=md5,
                step=step,
                field=field,
                value=er['extracted_value'],
                vendor_name=vendor,
                raw_text=raw_text,
                extraction_result_id=er['extraction_result_id'],
                _profiles_cache=profiles_cache,
            )
            all_results.extend(results)

            if not all_checks_pass(results):
                for r in results:
                    if r['check_result'] == 'FAIL':
                        check = r['check_name']
                        failures_by_check[check] = failures_by_check.get(check, 0) + 1
                        failures_by_vendor[vendor] = failures_by_vendor.get(vendor, 0) + 1
                        doc_failures.append(f"{field}:{check}:{r.get('detail','')}")

        checked += 1
        if doc_failures:
            failed += 1
            # Build review queue entry for this doc
            fail_cats = [f.split(':')[1] for f in doc_failures]
            primary_cat = f"VALIDATION_{fail_cats[0]}"
            detail_str = '; '.join(doc_failures)
            review_rows.append({
                'md5_hash': md5,
                'step': 7,
                'fail_category': primary_cat,
                'ai_suggestion': detail_str[:500],
                'suggestion_confidence': None,
                'suggestion_reason': None,
                'pdf_link': None,
                'notes': None,
            })
            gate_rows.append({'md5_hash': md5, 'step': 7, 'gate_status': 'BLOCKED'})
        else:
            passed += 1
            gate_rows.append({'md5_hash': md5, 'step': 7, 'gate_status': 'PASSED'})

        # Batch write every 5000 results
        if len(all_results) >= 5000:
            write_validation_results(all_results, conn=conn)
            conn.commit()
            log.info("Validation progress: %d/%d docs, %d results written (%.1fs)",
                     i + 1, len(doc_md5s), checked, time.time() - t0)
            all_results = []

    # Write remaining validation results
    if all_results:
        write_validation_results(all_results, conn=conn)
        conn.commit()

    # Write review queue entries for failures
    if review_rows:
        write_review_queue(review_rows, conn=conn)
        conn.commit()
        log.info("Validation: wrote %d review queue entries", len(review_rows))

    # Write gate results (PASSED or BLOCKED per doc)
    if gate_rows:
        write_gate_results(gate_rows, conn=conn)
        conn.commit()
        log.info("Validation: wrote %d gate results (%d passed, %d blocked)",
                 len(gate_rows), passed, failed)

    conn.close()
    elapsed = time.time() - t0

    summary = {
        'total': total,
        'checked': checked,
        'passed': passed,
        'failed': failed,
        'pass_rate': f'{passed/checked*100:.1f}%' if checked else 'N/A',
        'failures_by_check': failures_by_check,
        'failures_by_vendor': failures_by_vendor,
        'elapsed': f'{elapsed:.1f}s',
    }

    log.info("Validation complete: %d checked, %d passed (%.1f%%), %d failed (%.1fs)",
             checked, passed, passed / checked * 100 if checked else 0, failed, elapsed)

    return summary


# =============================================================================
# Run all steps
# =============================================================================

def run_all_steps(limit: int = None) -> dict:
    """Run all 6 steps sequentially with gate enforcement."""
    results = {}
    for step_num, step_fn in [
        (1, run_step_1),
        (2, run_step_2),
        (3, run_step_3),
        (4, run_step_4),
        (5, run_step_5),
        (6, run_step_6),
    ]:
        try:
            results[step_num] = step_fn(limit=limit)
        except GateBlockedError as e:
            print(f"\n  {e}")
            print(f"  Pipeline stopped at step {step_num}.")
            break
    return results


# =============================================================================
# Status
# =============================================================================

def pipeline_status() -> dict:
    """Get pipeline status with gate counts per step."""
    from .db_helpers import get_gate_status_summary
    summary = get_gate_status_summary()

    print(f"\n  Pipeline Status")
    print(f"  {'=' * 60}")
    print(f"  {'Step':<6} {'Name':<22} {'Passed':>8} {'Excluded':>8} {'Blocked':>8} {'Review':>8}")
    print(f"  {'-' * 6} {'-' * 22} {'-' * 8} {'-' * 8} {'-' * 8} {'-' * 8}")

    for step in range(1, 11):
        s = summary.get(step, {})
        if not s:
            continue
        name = STEP_NAMES.get(step, f'Step {step}')
        print(f"  {step:<6} {name:<22} {s.get('passed', 0):>8,} {s.get('excluded', 0):>8,} "
              f"{s.get('blocked', 0):>8,} {s.get('open_review', 0):>8,}")

    return summary


# =============================================================================
# Review display (DB-driven)
# =============================================================================

def review_step_db(step: int, vendor_filter: str = None) -> None:
    """Display review queue for a step, grouped by vendor + fail_category."""
    from .db_helpers import get_review_queue

    rows = get_review_queue(step, status='OPEN')

    if not rows:
        print(f"\n  Step {step}: {STEP_NAMES[step]}")
        print(f"  {'=' * 50}")
        print(f"  No open review items. Gate is CLEAR.")
        return

    # Get vendor info for each row
    md5_list = [r['md5_hash'] for r in rows]
    vendor_map = get_extraction_values_batch(md5_list, 'detected_vendor') if step > 2 else {}

    # Group by vendor + fail_category
    groups = {}
    for r in rows:
        vendor = vendor_map.get(r['md5_hash'], '(unknown)')
        key = (vendor, r['fail_category'])
        groups.setdefault(key, []).append(r)

    print(f"\n  Step {step}: {STEP_NAMES[step]} — Review ({len(rows)} open)")
    print(f"  {'=' * 60}")
    print(f"  {'Vendor':<30s} {'Category':<22s} {'Count':>6}")
    print(f"  {'-' * 30} {'-' * 22} {'-' * 6}")

    for (vendor, cat), group_rows in sorted(groups.items(), key=lambda x: -len(x[1])):
        display_vendor = vendor if vendor_filter is None else vendor
        print(f"  {display_vendor:<30s} {cat:<22s} {len(group_rows):>6}")

    print(f"\n  Total: {len(rows)} open review items")
