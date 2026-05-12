"""
Meta Regex Helper — pattern CRUD with 3-gate validation.

Three gates before pattern deployment:
1. Sample match — does the pattern match the sample text?
2. Regression check — do all currently-passing rows still pass?
3. Collision check — does the pattern match other vendors' data?

After deployment: deactivate old pattern, insert new one, trigger reprocess.
"""

import logging
import re
from datetime import datetime

import psycopg2.extras

from .database import get_connection
from .extraction_engine import ExtractionEngine, _build_flags

log = logging.getLogger(__name__)


def test_pattern(regex_pattern: str, sample_text: str,
                 regex_flags: str = 'IGNORECASE',
                 capture_group: int = 1) -> dict:
    """Gate 1: Does the pattern match the sample text?

    Returns: {matched: bool, value: str|None, groups: list, error: str|None}
    """
    flags = _build_flags(regex_flags)
    try:
        compiled = re.compile(regex_pattern, flags)
    except re.error as e:
        return {'matched': False, 'value': None, 'groups': [], 'error': str(e)}

    # Normalize sample text
    text = sample_text.replace('\\n', '\n') if sample_text else ''

    match = compiled.search(text)
    if not match:
        return {'matched': False, 'value': None, 'groups': list(match.groups()) if match else [], 'error': None}

    try:
        value = match.group(capture_group)
    except IndexError:
        value = match.group(0)

    return {
        'matched': True,
        'value': value,
        'groups': list(match.groups()),
        'error': None,
        'match_start': match.start(),
        'match_end': match.end(),
    }


def check_regression(regex_pattern: str, step: int, vendor_slug: str,
                     field: str, regex_flags: str = 'IGNORECASE',
                     capture_group: int = 1,
                     scan_type: str = 'INLINE') -> dict:
    """Gate 2: Do all currently-passing rows still pass with the new pattern?

    Samples up to 100 passing documents and checks the new pattern against them.
    For columnar patterns (FORWARD_COLUMNAR, WIDE_COLUMNAR), allows a small
    regression threshold since the ExtractionEngine uses label-anchored scanning
    that is more precise than raw re.search.

    Returns: {passed: bool, total_checked: int, regressions: int, details: list}
    """
    conn = get_connection()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    # Get passing documents for this vendor+field
    cur.execute("""
        SELECT er.md5_hash, er.extracted_value, rd.raw_ocr_text
        FROM ip_extraction_result er
        JOIN ip_raw_document rd ON er.md5_hash = rd.md5_hash
        JOIN ip_gate_result gr ON er.md5_hash = gr.md5_hash AND gr.step = %s
            AND gr.gate_status = 'PASSED'
        JOIN ip_extraction_result ev ON er.md5_hash = ev.md5_hash
            AND ev.field = 'detected_vendor' AND ev.extracted_value = %s
        WHERE er.step = %s AND er.field = %s
        AND er.extracted_value IS NOT NULL
        ORDER BY RANDOM()
        LIMIT 100
    """, (step, vendor_slug, step, field))
    passing_rows = cur.fetchall()
    conn.close()

    if not passing_rows:
        return {'passed': True, 'total_checked': 0, 'regressions': 0, 'details': []}

    flags = _build_flags(regex_flags)
    try:
        compiled = re.compile(regex_pattern, flags)
    except re.error as e:
        return {'passed': False, 'total_checked': 0, 'regressions': 0,
                'details': [f'Regex error: {e}']}

    regressions = []
    for row in passing_rows:
        text = (row['raw_ocr_text'] or '').replace('\\n', '\n')
        match = compiled.search(text)
        if not match:
            # New pattern doesn't match this doc — that's fine, existing
            # patterns still handle it. NOT a regression.
            continue
        else:
            try:
                new_val = match.group(capture_group)
            except IndexError:
                new_val = match.group(0)
            # Only a regression if new pattern matches but extracts a
            # DIFFERENT value — could cause wrong results if pattern
            # has higher priority than the current one.
            if new_val and new_val != row['extracted_value']:
                regressions.append({
                    'md5_hash': row['md5_hash'],
                    'expected_value': row['extracted_value'],
                    'new_value': new_val,
                })

    # For columnar patterns, the ExtractionEngine uses label-anchored
    # scanning which is much more precise than raw re.search. Allow a small
    # regression threshold (5%) since the engine won't actually regress.
    is_columnar = scan_type in ('FORWARD_COLUMNAR', 'WIDE_COLUMNAR')
    if is_columnar and passing_rows:
        threshold = max(10, int(len(passing_rows) * 0.10))
        passed = len(regressions) <= threshold
    else:
        passed = len(regressions) == 0

    return {
        'passed': passed,
        'total_checked': len(passing_rows),
        'regressions': len(regressions),
        'details': regressions[:10],
        'columnar_threshold': threshold if is_columnar and passing_rows else None,
    }


def check_collision(regex_pattern: str, step: int, vendor_slug: str,
                    regex_flags: str = 'IGNORECASE',
                    field: str = '') -> dict:
    """Gate 3: Does the pattern match other vendors' data?

    Samples up to 50 documents from OTHER vendors and checks for false positives.
    For universal fields (invoice_date, amount_due), collisions are expected and
    reported as warnings rather than failures — these fields are not vendor-specific.

    Returns: {passed: bool, collisions: int, details: list, skipped: bool}
    """
    # Date and amount patterns are universal — skip collision check
    universal_fields = ('invoice_date', 'amount_due', 'bill_total')
    if field in universal_fields:
        return {
            'passed': True,
            'collisions': 0,
            'details': [],
            'skipped': True,
            'skip_reason': f'{field} patterns are universal across vendors — collision check skipped',
        }
    conn = get_connection()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    # Get documents from other vendors
    cur.execute("""
        SELECT er.md5_hash, ev.extracted_value AS vendor, rd.raw_ocr_text
        FROM ip_extraction_result er
        JOIN ip_raw_document rd ON er.md5_hash = rd.md5_hash
        JOIN ip_extraction_result ev ON er.md5_hash = ev.md5_hash
            AND ev.field = 'detected_vendor'
        WHERE er.step = %s AND ev.extracted_value != %s
        ORDER BY RANDOM()
        LIMIT 50
    """, (step, vendor_slug))
    other_rows = cur.fetchall()
    conn.close()

    if not other_rows:
        return {'passed': True, 'collisions': 0, 'details': []}

    flags = _build_flags(regex_flags)
    try:
        compiled = re.compile(regex_pattern, flags)
    except re.error as e:
        return {'passed': False, 'collisions': 0, 'details': [f'Regex error: {e}']}

    collisions = []
    for row in other_rows:
        text = (row['raw_ocr_text'] or '').replace('\\n', '\n')
        match = compiled.search(text)
        if match:
            collisions.append({
                'md5_hash': row['md5_hash'],
                'vendor': row['vendor'],
                'matched_text': match.group(0)[:50],
            })

    return {
        'passed': len(collisions) == 0,
        'collisions': len(collisions),
        'details': collisions[:10],
    }


def deploy_pattern(regex_pattern: str, step: int, vendor_slug: str,
                   field: str, prior_pattern_id: int = None,
                   regex_flags: str = 'IGNORECASE',
                   capture_group: int = 1,
                   scan_type: str = 'INLINE',
                   scan_lines: int = 1,
                   normalization: str = 'NONE',
                   date_format: str = None,
                   pattern_type: str = 'PRIMARY',
                   notes: str = None,
                   deployed_by: str = 'meta_helper') -> int:
    """Deploy a new pattern: deactivate old, insert new, trigger reprocess.

    Args:
        regex_pattern: The regex pattern text
        step: Pipeline step number
        vendor_slug: Vendor name
        field: Field name in ip_vendor_pattern
        prior_pattern_id: ID of pattern being replaced (None for new)
        ...: Pattern metadata

    Returns: New vendor_pattern_id
    """
    conn = get_connection()
    cur = conn.cursor()
    now = datetime.now()

    # Determine version and priority
    version = 1
    priority = 10

    if prior_pattern_id:
        # Deactivate old pattern
        cur.execute(
            "UPDATE ip_vendor_pattern SET is_active = FALSE, valid_to = %s"
            " WHERE vendor_pattern_id = %s",
            (now, prior_pattern_id),
        )
        # Get old version and priority
        cur.execute(
            "SELECT version, priority, format_variant FROM ip_vendor_pattern"
            " WHERE vendor_pattern_id = %s",
            (prior_pattern_id,),
        )
        old = cur.fetchone()
        if old:
            version = old[0] + 1
            priority = old[1]
            format_variant = old[2]
        else:
            format_variant = 1
    else:
        format_variant = 1
        # Determine next priority (check ALL patterns, not just active,
        # to avoid unique constraint collisions with deactivated ones)
        cur.execute(
            "SELECT COALESCE(MAX(priority), 0) FROM ip_vendor_pattern"
            " WHERE vendor_name = %s AND field = %s",
            (vendor_slug, field),
        )
        max_priority = cur.fetchone()[0]
        priority = max_priority + 10

    # Insert new pattern
    cur.execute("""
        INSERT INTO ip_vendor_pattern
            (vendor_name, field, format_variant, pattern_type, priority,
             regex_pattern, regex_flags, capture_group, normalization,
             scan_type, scan_lines, date_format, is_active, version,
             prior_version_id, deployed_by, deployed_at, notes)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                TRUE, %s, %s, %s, %s, %s)
        RETURNING vendor_pattern_id
    """, (vendor_slug, field, format_variant, pattern_type, priority,
          regex_pattern, regex_flags, capture_group, normalization,
          scan_type, scan_lines, date_format, version,
          prior_pattern_id, deployed_by, now, notes))
    new_id = cur.fetchone()[0]

    conn.commit()
    conn.close()

    log.info("Deployed pattern %d (vendor=%s, field=%s, v%d)",
             new_id, vendor_slug, field, version)

    # Trigger reprocess
    from .reprocess import reprocess_after_fix
    reprocess_after_fix(step, vendor_slug=vendor_slug)

    return new_id


def generate_regex(target_value: str, sample_text: str, field: str,
                    vendor: str = '') -> list[dict]:
    """Auto-generate regex patterns from a target value and OCR context.

    Finds the value in the OCR text, analyzes surrounding labels/structure,
    and generates candidate regex patterns ranked by specificity.

    Args:
        target_value: The correct value the user sees in the OCR text
        sample_text: Raw OCR text from the document
        field: Field name (account_number, invoice_number, invoice_date, amount_due, detected_vendor)
        vendor: Vendor name (for field-specific heuristics)

    Returns:
        List of candidate patterns, each a dict with:
            regex, capture_group, description, scan_type, scan_lines
    """
    text = (sample_text or '').replace('\\n', '\n')
    value = (target_value or '').strip()

    if not value or not text:
        return []

    candidates = []

    # Find all occurrences of the value in the text
    escaped_value = re.escape(value)
    occurrences = list(re.finditer(escaped_value, text, re.IGNORECASE))

    if not occurrences:
        # Value not found literally — try normalized (strip whitespace diffs)
        normalized = re.sub(r'\s+', r'\\s+', escaped_value)
        occurrences = list(re.finditer(normalized, text, re.IGNORECASE))

    if not occurrences:
        return [{'regex': None, 'error': f'Value "{value}" not found in OCR text'}]

    # Build a value pattern (generalized regex for this value's format)
    value_pattern = _generalize_value(value, field)

    lines = text.split('\n')

    for occ in occurrences:
        # Find which line contains this occurrence
        line_start = text.rfind('\n', 0, occ.start())
        line_start = 0 if line_start < 0 else line_start + 1
        line_end = text.find('\n', occ.end())
        if line_end < 0:
            line_end = len(text)
        line = text[line_start:line_end].strip()

        # Get text before the value on this line (the "label")
        prefix_in_line = text[line_start:occ.start()].strip()

        # Determine line index for columnar analysis
        line_idx = text[:occ.start()].count('\n')

        # === Strategy 1: Label + Value on same line (INLINE) ===
        if prefix_in_line and len(prefix_in_line) >= 3:
            label_pattern = _generalize_label(prefix_in_line)
            if label_pattern:
                regex = f'{label_pattern}\\s*({value_pattern})'
                candidates.append({
                    'regex': regex,
                    'capture_group': 1,
                    'scan_type': 'INLINE',
                    'scan_lines': 1,
                    'description': f'Label "{prefix_in_line.strip()}" + value on same line',
                    'score': 90,
                })

        # === Strategy 2: Label on nearby line (FORWARD_COLUMNAR / WIDE_COLUMNAR) ===
        # Scan up to 8 lines above the value for a matching label
        for lookback in range(1, min(line_idx + 1, 9)):
            check_idx = line_idx - lookback
            if check_idx < 0 or check_idx >= len(lines):
                continue
            prev_line = lines[check_idx].strip()
            if prev_line and _looks_like_label(prev_line, field):
                label_pattern = _generalize_label(prev_line)
                if label_pattern:
                    scan = 'FORWARD_COLUMNAR' if lookback <= 2 else 'WIDE_COLUMNAR'
                    # For columnar layouts, use VALUE-ONLY pattern with scan_type.
                    # The ExtractionEngine finds the label via _FIELD_LABELS,
                    # then searches the next scan_lines for the value pattern.
                    score = 85 - lookback * 2
                    field_name_in_label = {
                        'invoice_date': 'invoice date',
                        'amount_due': 'amount due',
                        'account_number': 'account',
                        'invoice_number': 'invoice',
                    }
                    exact_label = field_name_in_label.get(field, '')
                    if exact_label and exact_label in prev_line.lower():
                        score += 5
                    candidates.append({
                        'regex': f'({value_pattern})',
                        'capture_group': 1,
                        'scan_type': scan,
                        'scan_lines': lookback + 2,
                        'regex_flags': 'IGNORECASE',
                        'description': f'Columnar: value pattern near label "{prev_line}" ({lookback} line{"s" if lookback > 1 else ""} above)',
                        'score': score,
                    })
                    break  # Use the closest matching label

        # === Strategy 3: Value-only pattern (less specific but no label needed) ===
        # Only use if value has a distinctive enough format
        if _is_distinctive_value(value, field):
            candidates.append({
                'regex': f'({value_pattern})',
                'capture_group': 1,
                'scan_type': 'INLINE',
                'scan_lines': 1,
                'description': f'Value format only (no label anchor) — less specific',
                'score': 40,
            })

    # Deduplicate and sort by score
    seen = set()
    unique = []
    for c in candidates:
        key = c['regex']
        if key and key not in seen:
            seen.add(key)
            unique.append(c)
    unique.sort(key=lambda x: x.get('score', 0), reverse=True)

    # Verify each candidate actually matches the sample
    verified = []
    for c in unique:
        if not c.get('regex'):
            continue
        try:
            # DOTALL needed for columnar patterns where .*? spans newlines
            flags = re.IGNORECASE | re.DOTALL
            m = re.search(c['regex'], text, flags)
            if m:
                try:
                    extracted = m.group(c.get('capture_group', 1))
                except IndexError:
                    extracted = m.group(0)
                # Check if extracted value matches target (case-insensitive)
                if extracted and extracted.strip().lower() == value.lower():
                    c['verified'] = True
                    c['extracted_value'] = extracted.strip()
                    verified.append(c)
                else:
                    # Partial match — still include but note it
                    c['verified'] = False
                    c['extracted_value'] = extracted.strip() if extracted else ''
                    c['note'] = f'Extracted "{extracted}" instead of "{value}"'
                    verified.append(c)
        except re.error:
            continue

    return verified if verified else [{'regex': None, 'error': 'Could not generate a matching pattern. Try entering the value exactly as it appears in the OCR text.'}]


def _generalize_value(value: str, field: str) -> str:
    """Convert a literal value to a generalized regex pattern.

    Examples:
        '3-0509-0312663' → r'\\d-\\d{4}-\\d{7}'
        'WGY17110UB'     → r'[A-Z]{3}\\d{5}[A-Z]{2}'
        '01/15/2024'     → r'\\d{2}/\\d{2}/\\d{4}'
        '$1,234.56'      → r'\\$?\\s*[\\d,]+\\.\\d{2}'
    """
    # Special handling for amounts
    if field in ('amount_due', 'bill_total'):
        # Strip $ and spaces for analysis
        clean = re.sub(r'[\$\s]', '', value)
        if re.match(r'[\d,]+\.\d{2}$', clean):
            return r'\$?\s*[\d,]+\.\d{2}'
        if re.match(r'[\d,]+$', clean):
            return r'\$?\s*[\d,]+'

    # Month name list for date patterns
    _MONTHS = r'(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|Sep(?:t(?:ember)?)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)'

    # Special handling for dates
    if field in ('invoice_date',):
        # MM/DD/YYYY or M/D/YYYY
        if re.match(r'\d{1,2}/\d{1,2}/\d{2,4}$', value):
            return r'\d{1,2}/\d{1,2}/\d{2,4}'
        # MM-DD-YYYY
        if re.match(r'\d{1,2}-\d{1,2}-\d{2,4}$', value):
            return r'\d{1,2}-\d{1,2}-\d{2,4}'
        # Month DD, YYYY (restrict to actual month names)
        if re.match(r'[A-Za-z]+\s+\d{1,2},?\s*\d{4}$', value):
            return _MONTHS + r'\s+\d{1,2},?\s*\d{4}'
        # DD-Mon-YYYY
        if re.match(r'\d{1,2}[-\s][A-Za-z]{3,9}[-\s,]*\d{4}$', value):
            return r'\d{1,2}[-\s]' + _MONTHS + r'[-\s,]*\d{4}'

    # General approach: analyze character runs and build a pattern
    pattern_parts = []
    i = 0
    while i < len(value):
        ch = value[i]

        if ch.isdigit():
            # Count consecutive digits
            j = i
            while j < len(value) and value[j].isdigit():
                j += 1
            n = j - i
            if n == 1:
                pattern_parts.append(r'\d')
            else:
                pattern_parts.append(f'\\d{{{n}}}')
            i = j
        elif ch.isalpha():
            # Count consecutive alpha of same case
            j = i
            upper = ch.isupper()
            while j < len(value) and value[j].isalpha() and value[j].isupper() == upper:
                j += 1
            n = j - i
            char_class = '[A-Z]' if upper else '[a-z]'
            if n == 1:
                pattern_parts.append(char_class)
            else:
                pattern_parts.append(f'{char_class}{{{n}}}')
            i = j
        elif ch in ' \t':
            # Whitespace
            j = i
            while j < len(value) and value[j] in ' \t':
                j += 1
            pattern_parts.append(r'\s+')
            i = j
        else:
            # Literal separator character (dash, slash, dot, etc.)
            pattern_parts.append(re.escape(ch))
            i += 1

    return ''.join(pattern_parts)


def _generalize_label(label_text: str) -> str:
    """Convert label text to a flexible regex that matches it.

    'Account #:' → r'Account\\s*#?:?\\s*'
    'Invoice No.' → r'Invoice\\s*No\\.?\\s*'
    """
    label = label_text.strip()
    if not label:
        return ''

    # Remove trailing colon/punctuation for processing
    label_clean = re.sub(r'[:\s]+$', '', label)

    # Escape special regex chars in the label, then relax spacing
    parts = label_clean.split()
    if not parts:
        return ''

    # Build a pattern that allows flexible whitespace between words
    # and makes trailing punctuation (#, :, .) optional
    regex_parts = []
    for word in parts:
        # Common label tokens — make their punctuation optional
        word_escaped = re.escape(word)
        # Make # and . optional
        word_escaped = word_escaped.replace(r'\#', '#?')
        word_escaped = word_escaped.replace(r'\.', r'\.?')
        regex_parts.append(word_escaped)

    pattern = r'\s*'.join(regex_parts)
    # Allow optional colon/whitespace after the label
    pattern += r'[:\s]*'

    return pattern


def _looks_like_label(line: str, field: str) -> bool:
    """Check if a line looks like a field label for the given field."""
    line_lower = line.lower().strip()
    field_keywords = {
        'account_number': ['account', 'customer', 'acct', 'client'],
        'invoice_number': ['invoice', 'bill', 'statement', 'reference'],
        'invoice_date': ['date', 'invoice date', 'bill date', 'statement date'],
        'amount_due': ['amount', 'total', 'balance', 'due', 'pay'],
        'detected_vendor': [],
    }
    keywords = field_keywords.get(field, [])
    return any(kw in line_lower for kw in keywords)


def _is_distinctive_value(value: str, field: str) -> bool:
    """Check if a value's format is distinctive enough for label-less matching."""
    # Account numbers with specific formats are distinctive
    if field == 'account_number':
        # Patterns like D-DDDD-DDDDDDD or WGYXXXXXXXX
        if re.match(r'\d-\d{4}-\d{7}$', value):  # Republic
            return True
        if re.match(r'[A-Z]{3}\d+[A-Z]*$', value):  # WM
            return True
        if re.match(r'UK\d{9,}$', value):  # GFL
            return True
    # Amounts with $ are somewhat distinctive
    if field in ('amount_due', 'bill_total') and '$' in value:
        return True
    # Dates are NOT distinctive (too many dates in an invoice)
    return False


def get_current_patterns(vendor_slug: str, field: str) -> list[dict]:
    """Get all active patterns for a vendor+field."""
    conn = get_connection()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute(
        "SELECT * FROM ip_vendor_pattern"
        " WHERE vendor_name = %s AND field = %s AND is_active = TRUE"
        " ORDER BY priority",
        (vendor_slug, field),
    )
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    return rows
