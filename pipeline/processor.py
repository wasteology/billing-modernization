"""
Invoice processing pipeline — 5-step OCR document processing with AI-assisted HITL review.

Each step runs independently with human review between:

  Step 1 (ocr):     validate OCR quality, flag non-invoices
  Step 2 (vendor):  detect_vendor() on raw OCR text
  Step 3 (account): extract_account() using detected vendor
  Step 4 (lookup):  check if account exists in account_number_resolution
  Step 5 (address): extract service address, match against services_current

HITL Review Loop:
  Run Step → Engine succeeds → pass through
           → Engine fails → AI pre-validation layer
               → confidence=auto: COI/W-9/vendor_profile auto-excluded
               → confidence=suggested: AI has a candidate for human review
               → confidence=manual: Human investigates OCR text

  Human reviews → provides corrections/clues
    → Engine-fixable: value feeds back to parsing_engines (pattern update)
    → One-off: override (exclude/skip)

  0 unresolved failures → proceed to next step

CRITICAL RULE — ACCOUNT EXTRACTION BEFORE ADDRESS FALLBACK:

  If an account number exists on an invoice, we MUST extract it. The account
  number is the ONLY reliable path to a known service_id. Address matching
  (step 5) is a LAST RESORT for invoices that genuinely have no account number.

All data files live under src/invoice_processing/data/:
  data/review/step1_ocr_review.csv      — OCR validation failures
  data/review/step2_vendor_review.csv   — Vendor detection failures
  data/review/step3_account_review.csv  — Account extraction failures
  data/review/step4_lookup_review.csv   — Account resolution failures
  data/review/step5_address_review.csv  — Address matching failures
  data/corrections/invoice_overrides.csv — Persistent one-off corrections
  data/output/invoice_processing.csv     — Accumulated pipeline results
"""

import csv
import json
import logging
import os
import re
import sys
import time
from collections import defaultdict
from pathlib import Path

import psycopg2.extras

from .database import get_connection

log = logging.getLogger(__name__)

DATA_DIR = Path(__file__).parent / "data"
OUTPUT_PATH = DATA_DIR / "output" / "invoice_processing.csv"
OVERRIDES_PATH = DATA_DIR / "corrections" / "invoice_overrides.csv"

# Per-step review file paths
STEP1_REVIEW_PATH = DATA_DIR / "review" / "step1_ocr_review.csv"
STEP2_REVIEW_PATH = DATA_DIR / "review" / "step2_vendor_review.csv"
STEP3_REVIEW_PATH = DATA_DIR / "review" / "step3_account_review.csv"
STEP4_REVIEW_PATH = DATA_DIR / "review" / "step4_lookup_review.csv"
STEP5_REVIEW_PATH = DATA_DIR / "review" / "step5_address_review.csv"

# Per-step review schemas
STEP1_FIELDS = [
    "md5_hash", "sp_created_date", "fail_category", "confidence",
    "ai_action", "human_action", "notes", "raw_ocr_text",
]
STEP2_FIELDS = [
    "md5_hash", "sp_created_date", "fail_category", "suggestion",
    "confidence", "human_action", "corrected_value", "notes", "raw_ocr_text",
]
STEP3_FIELDS = [
    "md5_hash", "sp_created_date", "detected_vendor", "fail_category",
    "suggestion", "account_format", "confidence", "human_action",
    "corrected_value", "notes", "invoice_image", "raw_ocr_text",
]
STEP4_FIELDS = [
    "md5_hash", "sp_created_date", "detected_vendor", "hauler_account_number",
    "fail_category", "notes", "invoice_image", "raw_ocr_text",
]
STEP5_FIELDS = [
    "md5_hash", "sp_created_date", "detected_vendor", "fail_category",
    "extracted_address", "notes", "raw_ocr_text",
]

OUTPUT_FIELDS = [
    "md5_hash", "sp_created_date", "ocr_status",
    "detected_vendor", "hauler_account_number",
    "match_method", "matched_service_id", "service_address",
    "excluded",
]

OVERRIDE_FIELDS = [
    "type", "match_field", "match_value", "action", "corrected_value", "notes",
]

# Non-invoice document patterns with confidence tiers
# auto: unambiguous non-invoices (applied automatically on re-run)
# suggested: usually not invoices but could be (human confirms)
NON_INVOICE_PATTERNS = [
    (r"CERTIFICATE OF (?:LIABILITY )?INSURANCE", "certificate_of_insurance", "auto"),
    (r"Request for Taxpayer.*Identification Number", "w9_form", "auto"),
    (r"VENDOR PROFILE\b", "vendor_profile", "auto"),
    (r"\bW-?9\b.*Internal Revenue", "w9_form", "auto"),
    (r"Form\s+W-?9\b", "w9_form", "auto"),
    (r"implementing a price increase of", "price_increase_letter", "suggested"),
    (r"we will be implementing a.{0,20}price increase", "price_increase_letter", "suggested"),
    (r"\bStatement\b.*\bCurrent\b.*\b(?:Past\s+Due|Days)\b", "statement", "suggested"),
]
_NON_INVOICE_RE = [
    (re.compile(p, re.IGNORECASE | re.DOTALL), label, confidence)
    for p, label, confidence in NON_INVOICE_PATTERNS
]

# Categories that auto-resolve (confidence=auto, ai_action=exclude)
_AUTO_EXCLUDE_CATEGORIES = frozenset({
    "certificate_of_insurance", "w9_form", "vendor_profile",
})

# Minimum text length for usable OCR
MIN_OCR_LENGTH = 50


# =========================================================================
# Gate enforcement — block downstream steps if upstream has unresolved failures
# =========================================================================

# Step N requires step N-1 to be clean
_STEP_PREREQUISITES = {
    "vendor":  "ocr",
    "account": "vendor",
    "lookup":  "account",
    "address": "lookup",
}

def _check_gate(step_name: str) -> bool:
    """Verify prior step has 0 unresolved failures. Returns True if clear."""
    prereq = _STEP_PREREQUISITES.get(step_name)
    if not prereq:
        return True  # step 1 (ocr) has no prerequisite

    cfg = _STEP_CONFIG[prereq]
    review_path = cfg["review_path"]

    if not review_path.exists():
        # No review file = step not run yet
        print(f"\n  GATE BLOCKED: Step '{prereq}' has not been run yet.")
        print(f"  Run: process-invoices {prereq}")
        return False

    rows = _load_review_rows(review_path)
    if not rows:
        return True  # 0 review items = clean

    unresolved = _count_unresolved(rows, cfg)
    if unresolved > 0:
        print(f"\n  GATE BLOCKED: {unresolved} unresolved failures at step '{prereq}'.")
        print(f"  Fix engines and re-run, or resolve in: {review_path}")
        print(f"  Then: process-invoices {step_name}")
        return False

    return True


# =========================================================================
# Helpers — overrides, working data, snippets
# =========================================================================

def _load_overrides(step: str) -> tuple[dict, set, set]:
    """Load overrides for a specific step.

    Returns:
        corrections: {md5_hash: corrected_value}
        exclusions:  set of md5_hashes to exclude entirely
        skips:       set of md5_hashes to skip (acknowledged, no failure)
    """
    if not OVERRIDES_PATH.exists():
        return {}, set(), set()

    corrections = {}
    exclusions = set()
    skips = set()

    with open(OVERRIDES_PATH, newline='', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            override_type = (row.get('type') or '').strip()
            match_field = (row.get('match_field') or '').strip()
            match_value = (row.get('match_value') or '').strip()
            action = (row.get('action') or '').strip()
            corrected = (row.get('corrected_value') or '').strip()

            if match_field != 'md5_hash' or not match_value:
                continue

            if action == 'exclude':
                exclusions.add(match_value)
            elif action == 'skip' and override_type == step:
                skips.add(match_value)
            elif action == 'set' and override_type == step:
                corrections[match_value] = corrected

    return corrections, exclusions, skips


def _ensure_overrides_template():
    """Create overrides CSV with headers if it doesn't exist."""
    if not OVERRIDES_PATH.exists():
        OVERRIDES_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(OVERRIDES_PATH, 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=OVERRIDE_FIELDS)
            writer.writeheader()


def _load_working_data() -> dict[str, dict]:
    """Load working CSV into {md5_hash: row_dict}."""
    if not OUTPUT_PATH.exists():
        return {}

    data = {}
    with open(OUTPUT_PATH, newline='', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            md5 = row.get('md5_hash', '').strip()
            if md5:
                data[md5] = row
    return data


def _save_working_data(data: dict[str, dict]):
    """Save working data dict to CSV."""
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    rows = sorted(data.values(), key=lambda r: (r.get('sp_created_date') or '', r.get('md5_hash') or ''))
    with open(OUTPUT_PATH, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=OUTPUT_FIELDS)
        writer.writeheader()
        writer.writerows(rows)


def _clean_ocr(text: str) -> str:
    """Full raw OCR text, cleaned for CSV storage."""
    if not text:
        return ""
    return text.replace('\r', '')


def _new_row(md5: str, sp_date: str, **kwargs) -> dict:
    """Create a new working data row with defaults."""
    row = {
        "md5_hash": md5, "sp_created_date": sp_date,
        "ocr_status": "", "detected_vendor": "",
        "hauler_account_number": "",
        "match_method": "", "matched_service_id": "", "service_address": "",
        "excluded": "",
    }
    row.update(kwargs)
    return row


# =========================================================================
# Helpers — per-step review file I/O with human decision carry-forward
# =========================================================================

def _load_prior_review(review_path: Path) -> dict[str, dict]:
    """Load prior human decisions from a step's review file.

    Returns {md5_hash: row_dict} for rows where any human-editable column
    (human_action, corrected_value, notes) has been filled in.
    """
    if not review_path.exists():
        return {}

    decisions = {}
    with open(review_path, newline='', encoding='utf-8', errors='replace') as f:
        reader = csv.DictReader(f)
        for row in reader:
            md5 = (row.get('md5_hash') or '').strip()
            if not md5:
                continue
            # Carry forward any row with human input
            has_input = any(
                (row.get(col) or '').strip()
                for col in ('human_action', 'corrected_value', 'notes')
            )
            if has_input:
                decisions[md5] = row
    return decisions


def _write_step_review(review_path: Path, fieldnames: list[str],
                       review_rows: list[dict], prior_decisions: dict[str, dict] = None,
                       sort_by: str = None):
    """Write a per-step review file.

    Merges prior human decisions onto still-failing rows. If a row appeared in
    a prior run with human_action set and still fails, the human decision is
    carried forward.
    """
    review_path.parent.mkdir(parents=True, exist_ok=True)
    prior = prior_decisions or {}

    # Carry forward human decisions for still-failing rows
    for row in review_rows:
        md5 = row.get('md5_hash', '')
        if md5 in prior:
            prior_row = prior[md5]
            # Carry forward human-written columns only
            for col in ('human_action', 'corrected_value', 'notes'):
                if col in prior_row and col in row:
                    prior_val = (prior_row.get(col) or '').strip()
                    current_val = (row.get(col) or '').strip()
                    if prior_val and not current_val:
                        row[col] = prior_val

    # Sort rows if requested
    if sort_by and review_rows:
        review_rows.sort(key=lambda r: (r.get(sort_by) or '').lower())

    with open(review_path, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(review_rows)
    _ensure_overrides_template()


# =========================================================================
# Step 1: OCR validation
# =========================================================================

FORM_FIELDS_PATH = DATA_DIR / "output" / "form_fields.json"


def _load_from_json_dir(json_dir) -> tuple[list[dict], dict]:
    """Load form parser JSON files from a local directory.

    For each JSON:
      - Extracts 'text' field → upserts into ocr_document
      - Extracts 'form_fields' → stored in form_fields.json for downstream use
      - Extracts 'tables' → stored alongside form_fields

    Returns:
        documents: list of {md5_hash, raw_text, sp_created_date} dicts
        form_fields_map: {md5: {form_fields: [...], tables: [...]}}
    """
    from pathlib import Path
    json_dir = Path(json_dir)

    json_files = sorted(json_dir.glob("*.json"))
    if not json_files:
        print(f"  No JSON files found in {json_dir}")
        return [], {}

    print(f"  Loading {len(json_files)} form parser JSONs from {json_dir}")

    documents = []
    form_fields_map = {}
    md5_list = []

    for jf in json_files:
        with open(jf, encoding='utf-8') as f:
            data = json.load(f)

        md5 = data.get('md5', jf.stem)
        text = data.get('text', '')
        form_fields = data.get('form_fields', [])
        tables = data.get('tables', [])

        md5_list.append(md5)
        documents.append({
            'md5_hash': md5,
            'raw_text': text,
            'sp_created_date': None,  # will be filled from DB
        })
        form_fields_map[md5] = {
            'form_fields': form_fields,
            'tables': tables,
        }

    # Upsert text into ocr_document and fetch sp_created_date
    conn = get_connection()
    cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    # Upsert raw_text (form parser text replaces existing)
    upsert_sql = """
        INSERT INTO ocr_document (md5_hash, raw_text)
        VALUES %s
        ON CONFLICT (md5_hash) DO UPDATE SET raw_text = EXCLUDED.raw_text
    """
    values = [(d['md5_hash'], d['raw_text']) for d in documents]
    psycopg2.extras.execute_values(cursor, upsert_sql, values, page_size=100)
    conn.commit()
    log.info("Upserted %d documents into ocr_document", len(values))

    # Fetch sp_created_date for these md5s
    cursor.execute(
        "SELECT md5_hash, sp_created_date FROM ocr_document WHERE md5_hash = ANY(%s)",
        (md5_list,),
    )
    date_map = {r['md5_hash']: r['sp_created_date'] for r in cursor.fetchall()}
    conn.close()

    for doc in documents:
        doc['sp_created_date'] = date_map.get(doc['md5_hash'])

    # Save form_fields for downstream steps
    FORM_FIELDS_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(FORM_FIELDS_PATH, 'w', encoding='utf-8') as f:
        json.dump(form_fields_map, f, indent=2)
    log.info("Saved form_fields to %s", FORM_FIELDS_PATH)

    return documents, form_fields_map


def step_ocr(batch_date: str = None, limit: int = None, json_dir=None) -> dict:
    """Step 1: Validate OCR quality and flag non-invoices.

    Confidence tiers:
      auto:      COI, W-9, vendor_profile → auto-excluded on re-run
      suggested: PI letter, statement → human confirms
      manual:    empty text → human decides

    On re-run:
      1. Override exclusions applied first
      2. Engine runs (patterns may have been updated)
      3. Prior human_action from review file honored
      4. confidence=auto items auto-excluded if no human override
      5. confidence=suggested/manual stay in review

    Args:
      json_dir: Path to directory of form parser JSON files. When provided,
                loads text from local JSONs, upserts into ocr_document,
                stores form_fields to data/output/form_fields.json,
                and processes ONLY those documents (fresh working data).
    """
    t0 = time.monotonic()

    # Load persistent overrides
    _, exclusions, _ = _load_overrides('ocr')
    if exclusions:
        log.info("Loaded %d exclusions", len(exclusions))

    # Load prior human decisions from step 1 review
    prior_decisions = _load_prior_review(STEP1_REVIEW_PATH)
    if prior_decisions:
        log.info("Loaded %d prior OCR review decisions", len(prior_decisions))

    if json_dir:
        documents, form_fields_map = _load_from_json_dir(json_dir)
    else:
        form_fields_map = {}
        # Fetch documents from DB
        conn = get_connection()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

        query = "SELECT md5_hash, raw_text, sp_created_date FROM ocr_document"
        params = []
        conditions = []

        if batch_date:
            conditions.append("sp_created_date = %s")
            params.append(batch_date)

        if conditions:
            query += " WHERE " + " AND ".join(conditions)
        query += " ORDER BY sp_created_date NULLS LAST"

        if limit:
            query += " LIMIT %s"
            params.append(limit)

        cursor.execute(query, params)
        documents = cursor.fetchall()
        conn.close()

    log.info("Documents to validate: %d", len(documents))

    # Fresh working data when loading from JSON dir; otherwise accumulate
    working = {} if json_dir else _load_working_data()
    review_rows = []
    totals = {
        "total": 0, "valid": 0, "excluded": 0, "empty": 0, "non_invoice": 0,
        "auto_excluded": 0, "human_excluded": 0, "human_included": 0,
    }

    for doc in documents:
        md5 = doc['md5_hash']
        raw_text = doc['raw_text'] or ''
        sp_date = str(doc['sp_created_date']) if doc['sp_created_date'] else ""

        totals["total"] += 1

        # Priority 1: Persistent override exclusion
        if md5 in exclusions:
            totals["excluded"] += 1
            working[md5] = _new_row(md5, sp_date, excluded="TRUE", ocr_status="excluded")
            continue

        # Check empty/too short
        text_clean = raw_text.replace('\\n', ' ').strip()
        if len(text_clean) < MIN_OCR_LENGTH:
            # Check prior human decision
            prior = prior_decisions.get(md5)
            if prior and (prior.get('human_action') or '').strip() == 'include':
                totals["valid"] += 1
                totals["human_included"] += 1
                working[md5] = _new_row(md5, sp_date, ocr_status="valid")
                continue
            if prior and (prior.get('human_action') or '').strip() == 'exclude':
                totals["human_excluded"] += 1
                working[md5] = _new_row(md5, sp_date, excluded="TRUE", ocr_status="empty")
                continue

            totals["empty"] += 1
            working[md5] = _new_row(md5, sp_date, ocr_status="empty")
            review_rows.append({
                "md5_hash": md5, "sp_created_date": sp_date,
                "fail_category": "empty_text",
                "confidence": "manual",
                "ai_action": "review",
                "human_action": "",
                "notes": "",
                "raw_ocr_text": _clean_ocr(raw_text),
            })
            continue

        # Check non-invoice patterns
        text_for_patterns = raw_text.replace('\\n', ' ')
        non_invoice_type = None
        confidence = None
        for pattern, label, conf in _NON_INVOICE_RE:
            if pattern.search(text_for_patterns):
                non_invoice_type = label
                confidence = conf
                break

        if non_invoice_type:
            # Check prior human decision
            prior = prior_decisions.get(md5)
            if prior:
                human_action = (prior.get('human_action') or '').strip()
                if human_action == 'include':
                    # Human overrode back to valid
                    totals["valid"] += 1
                    totals["human_included"] += 1
                    working[md5] = _new_row(md5, sp_date, ocr_status="valid")
                    continue
                if human_action == 'exclude':
                    totals["human_excluded"] += 1
                    working[md5] = _new_row(md5, sp_date, excluded="TRUE", ocr_status=non_invoice_type)
                    continue

            # Auto-resolve: confidence=auto categories excluded automatically
            if confidence == 'auto':
                totals["auto_excluded"] += 1
                totals["non_invoice"] += 1
                working[md5] = _new_row(md5, sp_date, excluded="TRUE", ocr_status=non_invoice_type)
                review_rows.append({
                    "md5_hash": md5, "sp_created_date": sp_date,
                    "fail_category": non_invoice_type,
                    "confidence": "auto",
                    "ai_action": "exclude",
                    "human_action": "",
                    "notes": "",
                    "raw_ocr_text": _clean_ocr(raw_text),
                })
                continue

            # Suggested: stays in review, not auto-excluded
            totals["non_invoice"] += 1
            working[md5] = _new_row(md5, sp_date, ocr_status=non_invoice_type)
            review_rows.append({
                "md5_hash": md5, "sp_created_date": sp_date,
                "fail_category": non_invoice_type,
                "confidence": "suggested",
                "ai_action": "exclude",
                "human_action": "",
                "notes": "",
                "raw_ocr_text": _clean_ocr(raw_text),
            })
            continue

        # Valid
        totals["valid"] += 1
        working[md5] = _new_row(md5, sp_date, ocr_status="valid")

        if totals["total"] % 10_000 == 0:
            log.info("  Processed %d / %d...", totals["total"], len(documents))

    _save_working_data(working)
    _write_step_review(STEP1_REVIEW_PATH, STEP1_FIELDS, review_rows, prior_decisions)

    elapsed = time.monotonic() - t0
    t = totals["total"]

    source = "form parser JSON" if json_dir else "ocr_document"
    print(f"\nStep 1: OCR Validation (source: {source})")
    print("=" * 50)
    print(f"  Total:           {t:>8,}")
    if t:
        print(f"  Valid:           {totals['valid']:>8,} ({totals['valid']/t*100:.1f}%)")
    print(f"  Empty/short:     {totals['empty']:>8,}")
    print(f"  Non-invoice:     {totals['non_invoice']:>8,}")
    if totals["excluded"]:
        print(f"  Override excl:   {totals['excluded']:>8,}")
    if totals["auto_excluded"]:
        print(f"  Auto-excluded:   {totals['auto_excluded']:>8,}  (COI/W-9/vendor_profile)")
    if totals["human_excluded"]:
        print(f"  Human excluded:  {totals['human_excluded']:>8,}")
    if totals["human_included"]:
        print(f"  Human included:  {totals['human_included']:>8,}  (overrode back to valid)")

    # Confidence breakdown
    conf_counts = defaultdict(int)
    for row in review_rows:
        conf_counts[row.get('confidence', '')] += 1
    if conf_counts:
        print(f"\n  Review breakdown:")
        for conf in ('auto', 'suggested', 'manual'):
            if conf_counts[conf]:
                print(f"    {conf}: {conf_counts[conf]}")

    if form_fields_map:
        # Show form_fields summary
        total_fields = sum(len(v['form_fields']) for v in form_fields_map.values())
        total_tables = sum(len(v['tables']) for v in form_fields_map.values())
        print(f"\n  Form parser data:")
        print(f"    Documents:     {len(form_fields_map):>8,}")
        print(f"    Form fields:   {total_fields:>8,}  (avg {total_fields/len(form_fields_map):.1f}/doc)")
        print(f"    Tables:        {total_tables:>8,}  (avg {total_tables/len(form_fields_map):.1f}/doc)")
        print(f"    Saved to:      {FORM_FIELDS_PATH}")

    print(f"\n  Review: {STEP1_REVIEW_PATH} ({len(review_rows)} rows)")
    print(f"  Output: {OUTPUT_PATH}")
    print(f"  Time: {elapsed:.1f}s")

    return totals


# =========================================================================
# Step 2: Vendor detection
# =========================================================================

def step_vendor() -> dict:
    """Step 2: Detect vendor from OCR text.

    Runs on documents with ocr_status='valid' from step 1.

    On failure, runs suggest_vendor() to provide a candidate for human review.

    Re-run read-back:
      1. Persistent overrides (corrections) applied first
      2. Engine runs (may have new patterns)
      3. Prior human_action honored: accept → use suggestion, set → use corrected_value
      4. No human decision → stays in review with suggestion
    """
    if not _check_gate("vendor"):
        return {"total": 0}

    t0 = time.monotonic()

    sys.path.insert(0, '/home/scstclair/projects/parsing_engines')
    from vendor_detection import detect_vendor

    from .suggestions import suggest_vendor

    corrections, _, _ = _load_overrides('vendor')
    if corrections:
        log.info("Loaded %d vendor overrides", len(corrections))

    prior_decisions = _load_prior_review(STEP2_REVIEW_PATH)
    if prior_decisions:
        log.info("Loaded %d prior vendor review decisions", len(prior_decisions))

    working = _load_working_data()
    if not working:
        print("  No working data. Run 'process-invoices ocr' first.")
        return {"total": 0}

    # Only process valid OCR docs
    valid_md5s = [md5 for md5, row in working.items() if row.get('ocr_status') == 'valid']
    if not valid_md5s:
        print("  No valid OCR documents. Run 'process-invoices ocr' first.")
        return {"total": 0}

    # Fetch raw text
    conn = get_connection()
    cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    log.info("Fetching raw text for %d documents...", len(valid_md5s))
    raw_texts = {}
    for i in range(0, len(valid_md5s), 5_000):
        chunk = valid_md5s[i:i + 5_000]
        cursor.execute(
            "SELECT md5_hash, raw_text FROM ocr_document WHERE md5_hash = ANY(%s)",
            (chunk,),
        )
        for row in cursor.fetchall():
            raw_texts[row['md5_hash']] = row['raw_text']
    conn.close()

    review_rows = []
    totals = {
        "total": 0, "detected": 0, "overridden": 0, "failed": 0,
        "human_set": 0, "human_accepted": 0, "human_excluded": 0,
    }

    for md5 in valid_md5s:
        row = working[md5]
        raw_text = raw_texts.get(md5, '')
        sp_date = row.get('sp_created_date', '')

        totals["total"] += 1

        # Priority 1: Persistent override
        if md5 in corrections:
            row['detected_vendor'] = corrections[md5]
            totals["overridden"] += 1
            totals["detected"] += 1
            continue

        # Priority 2: Run engine (may have been updated since last run)
        vendor = detect_vendor(raw_text)

        if vendor and vendor != "OTHER":
            # Engine now handles it — failure cleared
            row['detected_vendor'] = vendor
            totals["detected"] += 1
            continue

        # Engine failed — check prior human decisions
        prior = prior_decisions.get(md5)
        if prior:
            human_action = (prior.get('human_action') or '').strip()
            if human_action == 'set':
                corrected = (prior.get('corrected_value') or '').strip()
                if corrected:
                    row['detected_vendor'] = corrected
                    totals["human_set"] += 1
                    totals["detected"] += 1
                    continue
            elif human_action == 'accept':
                suggestion = (prior.get('suggestion') or '').strip()
                if suggestion:
                    row['detected_vendor'] = suggestion
                    totals["human_accepted"] += 1
                    totals["detected"] += 1
                    continue
            elif human_action == 'exclude':
                row['excluded'] = 'TRUE'
                row['ocr_status'] = 'excluded'
                totals["human_excluded"] += 1
                continue

        # No resolution — generate suggestion and add to review
        totals["failed"] += 1
        candidate, source = suggest_vendor(raw_text)

        fail_category = "no_vendor_text" if not raw_text.strip() else "no_match"
        confidence = "suggested" if candidate else "manual"

        review_rows.append({
            "md5_hash": md5, "sp_created_date": sp_date,
            "fail_category": fail_category,
            "suggestion": candidate or "",
            "confidence": confidence,
            "human_action": "",
            "corrected_value": "",
            "notes": "",
            "raw_ocr_text": _clean_ocr(raw_text),
        })

        if totals["total"] % 10_000 == 0:
            log.info("  Processed %d / %d...", totals["total"], len(valid_md5s))

    _save_working_data(working)
    _write_step_review(STEP2_REVIEW_PATH, STEP2_FIELDS, review_rows, prior_decisions)

    elapsed = time.monotonic() - t0
    t = totals["total"]

    print(f"\nStep 2: Vendor Detection")
    print("=" * 50)
    print(f"  Total:           {t:>8,}")
    if t:
        print(f"  Detected:        {totals['detected']:>8,} ({totals['detected']/t*100:.1f}%)")
    print(f"  Failed:          {totals['failed']:>8,}")
    if totals["overridden"]:
        print(f"  Overrides:       {totals['overridden']:>8,}")
    if totals["human_set"]:
        print(f"  Human set:       {totals['human_set']:>8,}")
    if totals["human_accepted"]:
        print(f"  Human accepted:  {totals['human_accepted']:>8,}  (suggestion confirmed)")
    if totals["human_excluded"]:
        print(f"  Human excluded:  {totals['human_excluded']:>8,}")

    # Suggestion breakdown
    with_suggestion = sum(1 for r in review_rows if r.get('suggestion'))
    if review_rows:
        print(f"\n  Review breakdown:")
        print(f"    With suggestion: {with_suggestion}")
        print(f"    Manual review:   {len(review_rows) - with_suggestion}")

    print(f"\n  Review: {STEP2_REVIEW_PATH} ({len(review_rows)} rows)")
    print(f"  Output: {OUTPUT_PATH}")
    print(f"  Time: {elapsed:.1f}s")

    return totals


# =========================================================================
# Step 3: Account extraction
# =========================================================================

def step_account() -> dict:
    """Step 3: Extract account number using detected vendor.

    Runs on documents with a detected_vendor from step 2.

    On failure, runs suggest_account() and shows vendor's account format.

    Re-run read-back:
      1. Persistent overrides applied first
      2. Engine runs (may have new patterns)
      3. Prior human_action honored: accept, set, skip, no_account
      4. NO_ACCOUNT vendors auto-skipped
      5. No human decision → stays in review with suggestion
    """
    if not _check_gate("account"):
        return {"total": 0}

    t0 = time.monotonic()

    sys.path.insert(0, '/home/scstclair/projects/parsing_engines')
    from account_number.account_extraction_engine import extract_account, VENDOR_ACCOUNTS

    from .suggestions import suggest_account, get_account_format_display
    from .invoice_renderer import save_invoice_image, fetch_docai_json, _get_gcs_client

    BILLS_DIR = DATA_DIR / "bills" / "account"
    gcs_client = _get_gcs_client()

    corrections, _, skips = _load_overrides('account')
    if corrections:
        log.info("Loaded %d account overrides", len(corrections))
    if skips:
        log.info("Loaded %d account skips", len(skips))

    prior_decisions = _load_prior_review(STEP3_REVIEW_PATH)
    if prior_decisions:
        log.info("Loaded %d prior account review decisions", len(prior_decisions))

    working = _load_working_data()
    if not working:
        print("  No working data. Run 'process-invoices ocr' first.")
        return {"total": 0}

    # Only process docs with a detected vendor
    need_text = [
        md5 for md5, row in working.items()
        if row.get('detected_vendor') and row.get('excluded') != 'TRUE'
    ]

    if not need_text:
        print("  No documents with detected vendors. Run 'process-invoices vendor' first.")
        return {"total": 0}

    # Fetch raw text
    conn = get_connection()
    cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    log.info("Fetching raw text for %d documents...", len(need_text))
    raw_texts = {}
    for i in range(0, len(need_text), 5_000):
        chunk = need_text[i:i + 5_000]
        cursor.execute(
            "SELECT md5_hash, raw_text FROM ocr_document WHERE md5_hash = ANY(%s)",
            (chunk,),
        )
        for row in cursor.fetchall():
            raw_texts[row['md5_hash']] = row['raw_text']
    conn.close()

    review_rows = []
    totals = {
        "total": 0, "extracted": 0, "no_pattern": 0,
        "no_account": 0, "extraction_failed": 0, "overridden": 0,
        "skipped": 0, "human_set": 0, "human_accepted": 0,
    }

    for md5 in need_text:
        row = working[md5]
        vendor = row['detected_vendor']
        raw_text = raw_texts.get(md5, '')
        sp_date = row.get('sp_created_date', '')

        # Clear stale account values from previous runs
        row['hauler_account_number'] = ''

        totals["total"] += 1

        # Priority 1: Persistent override
        if md5 in corrections:
            row['hauler_account_number'] = corrections[md5]
            totals["overridden"] += 1
            totals["extracted"] += 1
            continue

        if md5 in skips:
            totals["skipped"] += 1
            continue

        # NO_ACCOUNT vendor: auto-skip
        if vendor in VENDOR_ACCOUNTS and not VENDOR_ACCOUNTS[vendor]['has_account']:
            totals["no_account"] += 1
            continue

        # Priority 2: Run engine
        if vendor in VENDOR_ACCOUNTS:
            account = extract_account(vendor, raw_text)
            if account:
                row['hauler_account_number'] = account
                totals["extracted"] += 1
                continue
            fail_category = "extraction_failed"
        else:
            fail_category = "no_pattern"

        # Engine failed — check prior human decisions
        prior = prior_decisions.get(md5)
        if prior:
            human_action = (prior.get('human_action') or '').strip()
            corrected = (prior.get('corrected_value') or '').strip()
            suggestion = (prior.get('suggestion') or '').strip()

            # Infer action: corrected_value present → 'set',
            # no correction but suggestion exists → 'accept'
            if not human_action and corrected:
                human_action = 'set'
            elif not human_action and suggestion:
                human_action = 'accept'

            if human_action == 'set':
                if corrected:
                    row['hauler_account_number'] = corrected
                    totals["human_set"] += 1
                    totals["extracted"] += 1
                    continue
            elif human_action == 'accept':
                if suggestion:
                    row['hauler_account_number'] = suggestion
                    totals["human_accepted"] += 1
                    totals["extracted"] += 1
                    continue
            elif human_action == 'skip':
                totals["skipped"] += 1
                continue
            elif human_action == 'no_account':
                totals["no_account"] += 1
                continue

        # No resolution — generate suggestion and add to review
        if fail_category == "no_pattern":
            totals["no_pattern"] += 1
        else:
            totals["extraction_failed"] += 1

        candidate = suggest_account(vendor, raw_text, md5_hash=md5)
        acct_format = get_account_format_display(vendor)
        confidence = "suggested" if candidate else "manual"

        # Save actual invoice image for human review
        img_path = save_invoice_image(md5, BILLS_DIR, client=gcs_client)
        img_link = ""
        if img_path:
            # Relative path from review CSV location to the image
            rel = os.path.relpath(img_path, STEP3_REVIEW_PATH.parent)
            img_link = f'=HYPERLINK("{rel}","View Bill")'

        review_rows.append({
            "md5_hash": md5, "sp_created_date": sp_date,
            "detected_vendor": vendor,
            "fail_category": fail_category,
            "suggestion": candidate or "",
            "account_format": acct_format,
            "confidence": confidence,
            "human_action": "",
            "corrected_value": "",
            "notes": "",
            "invoice_image": img_link,
            "raw_ocr_text": _clean_ocr(raw_text),
        })

        if totals["total"] % 10_000 == 0:
            log.info("  Processed %d / %d...", totals["total"], len(need_text))

    _save_working_data(working)
    _write_step_review(STEP3_REVIEW_PATH, STEP3_FIELDS, review_rows, prior_decisions,
                       sort_by='detected_vendor')

    elapsed = time.monotonic() - t0
    t = totals["total"]
    has_pattern = t - totals["no_pattern"] - totals["no_account"]

    print(f"\nStep 3: Account Extraction")
    print("=" * 50)
    print(f"  With vendor:         {t:>8,}")
    print(f"  No pattern:          {totals['no_pattern']:>8,}")
    print(f"  NO_ACCOUNT vendor:   {totals['no_account']:>8,}")
    print(f"  Has pattern:         {has_pattern:>8,}")
    if has_pattern:
        print(f"  Extracted:           {totals['extracted']:>8,} "
              f"({totals['extracted']/has_pattern*100:.1f}% of has_pattern)")
    print(f"  Extraction failed:   {totals['extraction_failed']:>8,}")
    if totals["overridden"]:
        print(f"  Overrides:           {totals['overridden']:>8,}")
    if totals["skipped"]:
        print(f"  Skipped:             {totals['skipped']:>8,}")
    if totals["human_set"]:
        print(f"  Human set:           {totals['human_set']:>8,}")
    if totals["human_accepted"]:
        print(f"  Human accepted:      {totals['human_accepted']:>8,}  (suggestion confirmed)")

    # Suggestion breakdown by vendor
    if review_rows:
        from collections import defaultdict
        vendor_stats = defaultdict(lambda: {"suggested": 0, "manual": 0})
        for r in review_rows:
            v = r.get('detected_vendor', '?')
            if r.get('suggestion'):
                vendor_stats[v]["suggested"] += 1
            else:
                vendor_stats[v]["manual"] += 1

        with_suggestion = sum(s["suggested"] for s in vendor_stats.values())
        manual = sum(s["manual"] for s in vendor_stats.values())
        print(f"\n  Review breakdown ({len(review_rows)} failures):")
        print(f"    {'Vendor':<30s} {'Suggested':>9s} {'Manual':>8s}")
        print(f"    {'─' * 30} {'─' * 9} {'─' * 8}")
        for v in sorted(vendor_stats, key=str.lower):
            s = vendor_stats[v]
            print(f"    {v:<30s} {s['suggested']:>9d} {s['manual']:>8d}")
        print(f"    {'─' * 30} {'─' * 9} {'─' * 8}")
        print(f"    {'TOTAL':<30s} {with_suggestion:>9d} {manual:>8d}")

    print(f"\n  Review: {STEP3_REVIEW_PATH} ({len(review_rows)} rows)")
    print(f"  Output: {OUTPUT_PATH}")
    print(f"  Time: {elapsed:.1f}s")

    return totals


# =========================================================================
# Step 4: Account → service_id resolution
# =========================================================================

def step_lookup() -> dict:
    """Step 4: Resolve account numbers to service_id + service address.

    Looks up hauler_account_number in account_number_resolution to get
    service_id, then pulls the service address from services_current + location.
    """
    if not _check_gate("lookup"):
        return {"total": 0}

    t0 = time.monotonic()

    from .invoice_renderer import save_invoice_image, _get_gcs_client
    BILLS_DIR = DATA_DIR / "bills" / "lookup"
    gcs_client = _get_gcs_client()

    working = _load_working_data()
    if not working:
        print("  No working data. Run 'process-invoices ocr' first.")
        return {"total": 0}

    conn = get_connection()
    cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    # Build account → (service_id, address) lookup
    cursor.execute("""
        SELECT anr.hauler_account_number, anr.service_id,
               l.address, l.city, l.region, l.postal_code
        FROM account_number_resolution anr
        JOIN services_current sc ON anr.service_id = sc.service_id
        JOIN location l ON sc.location_id = l.location_id
        WHERE anr.is_active = TRUE
          AND anr.hauler_account_number IS NOT NULL
          AND anr.service_id IS NOT NULL
    """)
    # account → (service_id, formatted_address)
    account_lookup = {}
    for row in cursor.fetchall():
        acct = row['hauler_account_number']
        addr_parts = [row['address'] or '']
        if row['city']:
            addr_parts.append(row['city'])
        if row['region']:
            addr_parts.append(row['region'])
        if row['postal_code']:
            addr_parts.append(row['postal_code'])
        addr = ', '.join(p for p in addr_parts if p)
        if acct not in account_lookup:
            account_lookup[acct] = (str(row['service_id']), addr)
    conn.close()

    log.info("Account lookup entries: %d", len(account_lookup))

    review_rows = []
    failed_md5s = []
    totals = {"with_account": 0, "resolved": 0, "not_found": 0}

    for md5, row in working.items():
        account = (row.get('hauler_account_number') or '').strip()
        if row.get('excluded') == 'TRUE' or not account:
            continue

        totals["with_account"] += 1

        if account in account_lookup:
            sid, addr = account_lookup[account]
            row['match_method'] = "account"
            row['matched_service_id'] = sid
            row['service_address'] = addr
            totals["resolved"] += 1
        else:
            totals["not_found"] += 1
            failed_md5s.append(md5)

    # Fetch raw text for failed lookups
    raw_texts = {}
    if failed_md5s:
        conn2 = get_connection()
        cursor2 = conn2.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        for i in range(0, len(failed_md5s), 5_000):
            chunk = failed_md5s[i:i + 5_000]
            cursor2.execute(
                "SELECT md5_hash, raw_text FROM ocr_document WHERE md5_hash = ANY(%s)",
                (chunk,),
            )
            for r in cursor2.fetchall():
                raw_texts[r['md5_hash']] = r['raw_text']
        conn2.close()

    print(f"  Saving bill images for {len(failed_md5s)} unresolved accounts...")
    for md5 in failed_md5s:
        row = working[md5]

        img_path = save_invoice_image(md5, BILLS_DIR, client=gcs_client)
        img_link = ""
        if img_path:
            rel = os.path.relpath(img_path, STEP4_REVIEW_PATH.parent)
            img_link = f'=HYPERLINK("{rel}", "View Bill")'

        review_rows.append({
            "md5_hash": md5,
            "sp_created_date": row.get('sp_created_date', ''),
            "detected_vendor": row.get('detected_vendor', ''),
            "hauler_account_number": (row.get('hauler_account_number') or '').strip(),
            "fail_category": "account_not_found",
            "notes": "",
            "invoice_image": img_link,
            "raw_ocr_text": _clean_ocr(raw_texts.get(md5, '')),
        })

    _save_working_data(working)
    _write_step_review(STEP4_REVIEW_PATH, STEP4_FIELDS, review_rows,
                       sort_by='detected_vendor')

    elapsed = time.monotonic() - t0
    t = totals["with_account"]

    print(f"\nStep 4: Account Resolution")
    print("=" * 50)
    print(f"  With account:  {t:>8,}")
    if t:
        print(f"  Resolved:      {totals['resolved']:>8,} ({totals['resolved']/t*100:.1f}%)")
    print(f"  Not found:     {totals['not_found']:>8,}")
    print(f"\n  Review: {STEP4_REVIEW_PATH} ({len(review_rows)} rows)")
    print(f"  Output: {OUTPUT_PATH}")
    print(f"  Time: {elapsed:.1f}s")

    return totals


# =========================================================================
# Step 5: Composite key (vendor + address) resolution
# =========================================================================

_STREET_SUFFIX_MAP = {
    'avenue': 'ave', 'boulevard': 'blvd', 'circle': 'cir',
    'court': 'ct', 'drive': 'dr', 'expressway': 'expy',
    'highway': 'hwy', 'lane': 'ln', 'parkway': 'pkwy',
    'place': 'pl', 'road': 'rd', 'street': 'st',
    'terrace': 'ter', 'trail': 'trl', 'way': 'way',
}
_SUFFIX_RE = re.compile(
    r'\b(' + '|'.join(_STREET_SUFFIX_MAP.keys()) + r')\b', re.IGNORECASE,
)
_DIRECTIONAL_RE = re.compile(
    r'\b(northeast|northwest|southeast|southwest|north|south|east|west|ne|nw|se|sw|n|s|e|w)\b',
    re.IGNORECASE,
)
_UNIT_RE = re.compile(
    r'\s*\b(?:bldg|building|ste|suite|unit|apt|apartment)\s*[a-z0-9-]+\b', re.IGNORECASE,
)


def _normalize_address(addr: str) -> str:
    """Normalize address string for comparison."""
    if not addr:
        return ''
    s = addr.lower().strip()
    s = re.sub(r'\(.*?\)', '', s)
    s = re.sub(r'[.,#]', '', s)
    s = _SUFFIX_RE.sub(lambda m: _STREET_SUFFIX_MAP[m.group(1).lower()], s)
    s = _UNIT_RE.sub('', s)
    s = _DIRECTIONAL_RE.sub('', s)
    s = re.sub(r'\s+', ' ', s).strip()
    return s


def _extract_street_number(addr: str) -> str:
    """Extract the leading street number from an address."""
    m = re.match(r'^(\d+)', addr.strip())
    return m.group(1) if m else ''


def _build_service_address_index(cursor):
    """Build vendor+address lookup indexes from services_current."""
    cursor.execute("""
        SELECT v.vendor_name, l.address, l.city, l.region, l.postal_code,
               sc.service_id, sc.location_id
        FROM services_current sc
        JOIN vendor v ON sc.vendor_id = v.vendor_id
        JOIN location l ON sc.location_id = l.location_id
        WHERE l.address IS NOT NULL
          AND TRIM(l.address) != ''
          AND sc.is_active = TRUE
    """)
    svc_rows = cursor.fetchall()

    db_vendor_names = {(svc['vendor_name'] or '').lower().strip() for svc in svc_rows}
    db_vendor_names.discard('')

    street_lookup = defaultdict(list)
    zip_lookup = defaultdict(list)

    for svc in svc_rows:
        vname = (svc['vendor_name'] or '').lower().strip()
        addr = _normalize_address(svc['address'])
        if not vname or not addr:
            continue

        addr_parts = [svc['address'] or '']
        if svc['city']:
            addr_parts.append(svc['city'])
        if svc['region']:
            addr_parts.append(svc['region'])
        if svc['postal_code']:
            addr_parts.append(svc['postal_code'])
        full_addr = ', '.join(p for p in addr_parts if p)

        street_lookup[addr].append((vname, svc['service_id'], full_addr))

        postal = (svc['postal_code'] or '').strip().split('-')[0]
        street_num = _extract_street_number(addr)
        if postal and street_num:
            zip_lookup[(postal, street_num)].append((vname, svc['service_id'], full_addr))

    return street_lookup, zip_lookup, db_vendor_names


def _build_vendor_resolver(db_vendor_names):
    """Build a function that maps detected vendor → set of DB vendor names."""
    sys.path.insert(0, '/home/scstclair/projects/normalization_engines/src')
    from normalization_engines import VendorNormalizer
    vnorm = VendorNormalizer()

    def resolve(detected: str) -> set[str]:
        patterns = vnorm.get_db_patterns(detected)
        exact = vnorm.get_exact_matches(detected)
        matches = set()
        for e in exact:
            el = e.lower().strip()
            if el in db_vendor_names:
                matches.add(el)
        for pat in patterns:
            prefix = pat.rstrip('%').lower().strip()
            for dbv in db_vendor_names:
                if dbv.startswith(prefix):
                    matches.add(dbv)
        dl = detected.lower().strip()
        if dl in db_vendor_names:
            matches.add(dl)
        return matches

    return resolve


def step_address() -> dict:
    """Step 5: Resolve unmatched invoices via vendor + address composite key.

    Runs on all valid invoices not yet resolved by step 4 (account lookup).
    Extracts service address from OCR, then matches against services_current
    using vendor + address as composite key.

    Matching tiers:
      Tier 1 — Exact: normalized vendor + normalized street
      Tier 2 — Postal + street number: same vendor + zip + street number
    """
    if not _check_gate("address"):
        return {"total": 0}

    t0 = time.monotonic()

    sys.path.insert(0, '/home/scstclair/projects/parsing_engines')
    from service_address.service_address_engine import extract_service_address

    working = _load_working_data()
    if not working:
        print("  No working data. Run earlier steps first.")
        return {"total": 0}

    # Everything not yet resolved by account lookup
    unmatched = [
        md5 for md5, row in working.items()
        if not row.get('matched_service_id')
        and row.get('detected_vendor')
        and row.get('excluded') != 'TRUE'
        and row.get('ocr_status') == 'valid'
    ]

    if not unmatched:
        print("  No unmatched invoices to process.")
        return {"total": 0}

    log.info("Unmatched invoices for address resolution: %d", len(unmatched))

    # Fetch raw text
    conn = get_connection()
    cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    raw_texts = {}
    for i in range(0, len(unmatched), 5_000):
        chunk = unmatched[i:i + 5_000]
        cursor.execute(
            "SELECT md5_hash, raw_text FROM ocr_document WHERE md5_hash = ANY(%s)",
            (chunk,),
        )
        for row in cursor.fetchall():
            raw_texts[row['md5_hash']] = row['raw_text']

    # Build address indexes
    street_lookup, zip_lookup, db_vendor_names = _build_service_address_index(cursor)
    conn.close()

    resolve_vendor = _build_vendor_resolver(db_vendor_names)

    log.info("Address index: %d street keys, %d zip+street keys, %d DB vendors",
             len(street_lookup), len(zip_lookup), len(db_vendor_names))

    review_rows = []
    totals = {
        "total": 0, "extracted": 0, "matched_exact": 0,
        "matched_zip": 0, "no_extract": 0, "no_match": 0,
    }

    for md5 in unmatched:
        row = working[md5]
        vendor = row['detected_vendor']
        raw_text = raw_texts.get(md5, '')
        sp_date = row.get('sp_created_date', '')

        totals["total"] += 1

        # Extract service address from OCR
        addr_dict = extract_service_address(vendor, raw_text)

        if not addr_dict:
            totals["no_extract"] += 1
            review_rows.append({
                "md5_hash": md5, "sp_created_date": sp_date,
                "detected_vendor": vendor,
                "fail_category": "extraction_failed",
                "extracted_address": "",
                "notes": "",
                "raw_ocr_text": _clean_ocr(raw_text),
            })
            continue

        # Reject Wasteology's own billing address (false positive)
        street_lower = (addr_dict.get('street') or '').lower()
        if any(w in street_lower for w in ('shelbyville', 'st matthews', 'st. matthews')):
            totals["no_extract"] += 1
            review_rows.append({
                "md5_hash": md5, "sp_created_date": sp_date,
                "detected_vendor": vendor,
                "fail_category": "extracted_billing_address",
                "extracted_address": addr_dict.get('street', ''),
                "notes": "",
                "raw_ocr_text": _clean_ocr(raw_text),
            })
            continue

        totals["extracted"] += 1

        # Format extracted address for storage
        addr_parts = [addr_dict.get('street', '')]
        if addr_dict.get('city'):
            addr_parts.append(addr_dict['city'])
        if addr_dict.get('state'):
            addr_parts.append(addr_dict['state'])
        if addr_dict.get('postal_code'):
            addr_parts.append(addr_dict['postal_code'])
        extracted_full = ', '.join(p for p in addr_parts if p)

        # Resolve detected vendor → DB vendor names
        vendor_db_names = resolve_vendor(vendor)
        extracted_street = _normalize_address(addr_dict.get('street', ''))
        extracted_zip = (addr_dict.get('postal_code') or '').strip().split('-')[0]
        extracted_street_num = _extract_street_number(extracted_street)

        # Tier 1: Vendor + exact normalized street
        candidates = street_lookup.get(extracted_street, [])
        if candidates and vendor_db_names:
            matched = [(sid, fa) for vn, sid, fa in candidates if vn in vendor_db_names]
            if matched:
                sid, svc_addr = matched[0]
                row['match_method'] = "vendor_address_exact"
                row['matched_service_id'] = str(sid)
                row['service_address'] = svc_addr
                totals["matched_exact"] += 1
                continue

        # Tier 2: Vendor + postal code + street number
        if extracted_zip and extracted_street_num and vendor_db_names:
            candidates = zip_lookup.get((extracted_zip, extracted_street_num), [])
            matched = [(sid, fa) for vn, sid, fa in candidates if vn in vendor_db_names]
            if matched:
                sid, svc_addr = matched[0]
                row['match_method'] = "vendor_address_zip"
                row['matched_service_id'] = str(sid)
                row['service_address'] = svc_addr
                totals["matched_zip"] += 1
                continue

        # No match — store extracted address for review
        row['service_address'] = extracted_full
        totals["no_match"] += 1
        review_rows.append({
            "md5_hash": md5, "sp_created_date": sp_date,
            "detected_vendor": vendor,
            "fail_category": "address_not_matched",
            "extracted_address": extracted_full,
            "notes": "",
            "raw_ocr_text": _clean_ocr(raw_text),
        })

    _save_working_data(working)
    _write_step_review(STEP5_REVIEW_PATH, STEP5_FIELDS, review_rows,
                       sort_by='detected_vendor')

    elapsed = time.monotonic() - t0
    t = totals["total"]
    total_matched = totals["matched_exact"] + totals["matched_zip"]

    print(f"\nStep 5: Vendor + Address Resolution")
    print("=" * 50)
    print(f"  Unmatched invoices:  {t:>8,}")
    if t:
        print(f"  Address extracted:   {totals['extracted']:>8,} "
              f"({totals['extracted']/t*100:.1f}%)")
    print(f"  No extraction:       {totals['no_extract']:>8,}")
    print(f"  Matched (exact):     {totals['matched_exact']:>8,}")
    print(f"  Matched (zip+num):   {totals['matched_zip']:>8,}")
    if t:
        print(f"  Total matched:       {total_matched:>8,} "
              f"({total_matched/t*100:.1f}%)")
    print(f"  No match:            {totals['no_match']:>8,}")
    print(f"\n  Review: {STEP5_REVIEW_PATH} ({len(review_rows)} rows)")
    print(f"  Output: {OUTPUT_PATH}")
    print(f"  Time: {elapsed:.1f}s")

    # Overall summary
    total_docs = len(working)
    excluded = sum(1 for r in working.values() if r.get('excluded') == 'TRUE')
    valid = sum(1 for r in working.values() if r.get('ocr_status') == 'valid')
    resolved = sum(1 for r in working.values() if r.get('matched_service_id'))

    print(f"\nOverall Pipeline:")
    print(f"  Documents:     {total_docs:>8,}")
    if excluded:
        print(f"  Excluded:      {excluded:>8,}")
    if total_docs:
        print(f"  Valid OCR:     {valid:>8,} ({valid/total_docs*100:.1f}%)")
        print(f"  Resolved:      {resolved:>8,} ({resolved/total_docs*100:.1f}%)")
    by_method = defaultdict(int)
    for r in working.values():
        m = r.get('match_method', '')
        if m:
            by_method[m] += 1
    for method, cnt in sorted(by_method.items()):
        print(f"    {method}: {cnt:,}")

    return totals


# =========================================================================
# Review & Approve — HITL CLI commands
# =========================================================================

_STEP_CONFIG = {
    "ocr": {
        "name": "Step 1: OCR Validation",
        "review_path": STEP1_REVIEW_PATH,
        "fields": STEP1_FIELDS,
        "display_cols": ["md5_hash", "sp_created_date", "fail_category", "confidence", "ai_action", "human_action"],
        "has_human_action": True,
        "has_auto": True,
    },
    "vendor": {
        "name": "Step 2: Vendor Detection",
        "review_path": STEP2_REVIEW_PATH,
        "fields": STEP2_FIELDS,
        "display_cols": ["md5_hash", "sp_created_date", "fail_category", "suggestion", "confidence", "human_action"],
        "has_human_action": True,
        "has_auto": False,
    },
    "account": {
        "name": "Step 3: Account Extraction",
        "review_path": STEP3_REVIEW_PATH,
        "fields": STEP3_FIELDS,
        "display_cols": ["md5_hash", "sp_created_date", "detected_vendor", "fail_category", "suggestion", "account_format", "confidence", "human_action"],
        "has_human_action": True,
        "has_auto": False,
    },
    "lookup": {
        "name": "Step 4: Account Resolution",
        "review_path": STEP4_REVIEW_PATH,
        "fields": STEP4_FIELDS,
        "display_cols": ["md5_hash", "sp_created_date", "detected_vendor", "hauler_account_number", "fail_category"],
        "has_human_action": False,
        "has_auto": False,
    },
    "address": {
        "name": "Step 5: Address Resolution",
        "review_path": STEP5_REVIEW_PATH,
        "fields": STEP5_FIELDS,
        "display_cols": ["md5_hash", "sp_created_date", "detected_vendor", "fail_category", "extracted_address"],
        "has_human_action": False,
        "has_auto": False,
    },
}

# Column display widths
_COL_WIDTHS = {
    "md5_hash": 10,
    "sp_created_date": 12,
    "fail_category": 26,
    "confidence": 10,
    "ai_action": 9,
    "human_action": 13,
    "suggestion": 30,
    "corrected_value": 20,
    "detected_vendor": 24,
    "hauler_account_number": 20,
    "account_format": 18,
    "extracted_address": 40,
    "raw_ocr_text": 80,
}


def _count_unresolved(rows: list[dict], cfg: dict) -> int:
    """Count unresolved rows for a step."""
    if not cfg["has_human_action"]:
        # Steps 4-5: every row is unresolved
        return len(rows)

    count = 0
    for row in rows:
        human_action = (row.get('human_action') or '').strip()
        if human_action:
            continue  # resolved by human
        if cfg["has_auto"] and (row.get('confidence') or '').strip() == 'auto':
            continue  # auto-resolved
        count += 1
    return count


def _load_review_rows(review_path: Path) -> list[dict]:
    """Load all rows from a review CSV."""
    if not review_path.exists():
        return []
    with open(review_path, newline='', encoding='utf-8') as f:
        return list(csv.DictReader(f))


def review_step(step_name: str, show_all: bool = False, show_snippet: bool = False):
    """Display pending review items for a step.

    Args:
        step_name: ocr, vendor, account, lookup, or address
        show_all: show all rows including resolved (default: unresolved only)
        show_snippet: include raw_ocr_snippet column
    """
    cfg = _STEP_CONFIG[step_name]
    rows = _load_review_rows(cfg["review_path"])

    if not rows:
        print(f"\n{cfg['name']}")
        print("=" * 50)
        print("  No review file found. Run the step first.")
        return

    # Filter to unresolved unless --all
    if show_all:
        display_rows = rows
    else:
        display_rows = []
        for row in rows:
            human_action = (row.get('human_action') or '').strip()
            if human_action:
                continue
            if cfg["has_auto"] and (row.get('confidence') or '').strip() == 'auto':
                continue
            display_rows.append(row)

    total = len(rows)
    unresolved = _count_unresolved(rows, cfg)

    print(f"\n{cfg['name']} — Review")
    print("=" * 50)
    print(f"  Total in review:   {total}")
    print(f"  Unresolved:        {unresolved}")
    if cfg["has_auto"]:
        auto_count = sum(1 for r in rows if (r.get('confidence') or '') == 'auto')
        print(f"  Auto-resolved:     {auto_count}")
    if cfg["has_human_action"]:
        human_count = sum(1 for r in rows if (r.get('human_action') or '').strip())
        print(f"  Human resolved:    {human_count}")

    if not display_rows:
        label = "All items resolved." if total else "No items to review."
        print(f"\n  {label}")
        print(f"\n  File: {cfg['review_path']}")
        return

    # Build display columns
    cols = list(cfg["display_cols"])
    if show_snippet and "raw_ocr_text" in cfg["fields"]:
        cols.append("raw_ocr_text")

    # Print table header
    print()
    header_parts = [f"{'#':>3}"]
    for col in cols:
        w = _COL_WIDTHS.get(col, 20)
        label = col.replace('_', ' ').title()
        if col == "md5_hash":
            label = "MD5"
        elif col == "ai_action":
            label = "AI Action"
        elif col == "raw_ocr_text":
            label = "OCR Text"
        header_parts.append(f"{label:<{w}}")
    print("  " + " ".join(header_parts))
    print("  " + "-" * (4 + sum(_COL_WIDTHS.get(c, 20) + 1 for c in cols)))

    # Print rows
    for i, row in enumerate(display_rows, 1):
        parts = [f"{i:>3}"]
        for col in cols:
            w = _COL_WIDTHS.get(col, 20)
            val = (row.get(col) or '').strip()
            if col == "md5_hash":
                val = val[:8] + ".." if len(val) > 10 else val
            elif col == "raw_ocr_text":
                val = val.replace('\n', ' ')[:w]
            parts.append(f"{val:<{w}}")
        print("  " + " ".join(parts))

    print(f"\n  Showing {len(display_rows)} of {total} rows"
          + (" (unresolved only — use --all to see all)" if not show_all and total > len(display_rows) else ""))
    print(f"  File: {cfg['review_path']}")

    # Print guidance for steps with human_action
    if cfg["has_human_action"] and unresolved:
        print(f"\n  To resolve: edit the review CSV and set human_action column.")
        if step_name == "ocr":
            print("  Actions: include | exclude")
        elif step_name == "vendor":
            print("  Actions: accept | set (+ corrected_value) | exclude")
        elif step_name == "account":
            print("  Actions: accept | set (+ corrected_value) | skip | no_account")


def approve_step(step_name: str) -> bool:
    """Gate check: verify 0 unresolved failures before advancing to next step.

    Returns True if approved, False if unresolved items remain.
    """
    cfg = _STEP_CONFIG[step_name]
    rows = _load_review_rows(cfg["review_path"])

    step_order = ["ocr", "vendor", "account", "lookup", "address"]
    idx = step_order.index(step_name)
    next_step = step_order[idx + 1] if idx < len(step_order) - 1 else None

    print(f"\n{cfg['name']} — Gate Check")
    print("=" * 50)

    if not rows:
        # No review file = no failures (or step not run yet)
        if not cfg["review_path"].exists():
            print("  No review file found. Run the step first.")
            return False
        print("  0 review items. Step clear.")
        if next_step:
            print(f"\n  Ready for: process-invoices {next_step}")
        else:
            print("\n  Pipeline complete.")
        return True

    unresolved = _count_unresolved(rows, cfg)
    total = len(rows)

    if unresolved == 0:
        print(f"  {total} review items, 0 unresolved.")
        if cfg["has_auto"]:
            auto_count = sum(1 for r in rows if (r.get('confidence') or '') == 'auto')
            human_count = total - auto_count
            print(f"  Auto-resolved: {auto_count}, Human resolved: {human_count}")
        print("\n  APPROVED.")
        if next_step:
            print(f"  Ready for: process-invoices {next_step}")
        else:
            print("  Pipeline complete.")
        return True
    else:
        print(f"  {unresolved} UNRESOLVED out of {total} review items.")
        print(f"\n  BLOCKED. Resolve all items before proceeding.")
        print(f"  Run: process-invoices review {step_name}")
        return False
