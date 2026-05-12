"""Local field extractor — structured field extraction from Document AI OCR JSON.

Replicates Form Parser's form_fields and tables output using only the
data already present in base Document AI OCR JSON files ($0.0015/page
vs Form Parser's $0.03/page).

Approach:
- Raw OCR text is well-ordered (label\\nvalue\\n...) for most invoice layouts
- Sequential pairing with label-block grouping for side-by-side labels
- Value-type validation rejects mismatched pairings (date label → address value)
- Tear line detection stops processing at payment stub boundary
- Line-level bounding boxes used only for table column detection

Usage:
    python -m src.invoice_processing.field_extractor --json <file>
    python -m src.invoice_processing.field_extractor --validate
    python -m src.invoice_processing.field_extractor --input-dir <dir> --output-dir <dir>
"""

import json
import logging
import re
from pathlib import Path

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Text helpers (from old/invoice_renderer.py)
# ---------------------------------------------------------------------------

def _preprocess_text(raw_text: str) -> tuple[str, list[int]]:
    """Replace literal \\n with real newline. Returns (clean_text, index_map)."""
    clean = []
    orig_to_clean = []
    i = 0
    ci = 0
    while i < len(raw_text):
        if i + 1 < len(raw_text) and raw_text[i] == '\\' and raw_text[i + 1] == 'n':
            clean.append('\n')
            orig_to_clean.append(ci)
            orig_to_clean.append(ci)
            i += 2
            ci += 1
        else:
            clean.append(raw_text[i])
            orig_to_clean.append(ci)
            i += 1
            ci += 1
    orig_to_clean.append(ci)
    return ''.join(clean), orig_to_clean


def _get_text_from_layout(layout: dict, clean_text: str,
                          orig_to_clean: list[int]) -> str | None:
    """Extract text using textAnchor with index remapping."""
    segments = layout.get('textAnchor', {}).get('textSegments', [])
    if not segments:
        return None
    result = []
    for seg in segments:
        start = int(seg.get('startIndex', 0))
        end = int(seg.get('endIndex', 0))
        if end > start:
            cs = orig_to_clean[start]
            ce = orig_to_clean[end - 1] + 1
            result.append(clean_text[cs:ce])
    text = ''.join(result).replace('\n', ' ').strip()
    return text if text else None


def _get_bbox_normalized(layout: dict) -> dict | None:
    """Extract normalized bounding box {x, y, w, h}."""
    verts = layout.get('boundingPoly', {}).get('normalizedVertices', [])
    if len(verts) < 4:
        return None
    xs = [v.get('x', 0) for v in verts]
    ys = [v.get('y', 0) for v in verts]
    return {'x': min(xs), 'y': min(ys), 'w': max(xs) - min(xs), 'h': max(ys) - min(ys)}


# ---------------------------------------------------------------------------
# Tear line / noise detection
# ---------------------------------------------------------------------------

_TEAR_LINE_RE = re.compile(
    r'(?:please\s+detach|detach\s+(?:above|below|here)|return\s+this\s+portion'
    r'|tear\s+here|cut\s+(?:here|along)|return\s+(?:bottom|lower)\s+portion'
    r'|for\s+proper\s+credit\s+please\s+return)',
    re.IGNORECASE,
)

_NOISE_RE = re.compile(
    r'(?:make\s+checks\s+payable|www\.\S+|\.com\b|\.net\b'
    r'|^\d{13,}$|^Page\s+\d|MB\s+\d+\.\d+'
    r'|^\|[\.\-\xb7]+\|?$|^[☑☐✓✗]+$)',
    re.IGNORECASE,
)


def _is_noise(text: str) -> bool:
    return bool(_NOISE_RE.search(text))


# ---------------------------------------------------------------------------
# Label detection
# ---------------------------------------------------------------------------

# Regex patterns for label detection
_LABEL_INLINE_RE = re.compile(r'^(.+?)\s*:\s+(.+)$')
_LABEL_COLON_RE = re.compile(r'^(.+?)\s*:\s*$')
_LABEL_HASH_RE = re.compile(r'^(.+\S)\s*#\s*$')
_LABEL_NO_RE = re.compile(r'^(.+?)\s+(?:NO\.?|No\.?)\s*$', re.IGNORECASE)

# Known form-field labels (NO ambiguous table-header words like Date, Amount, Description)
_KNOWN_LABELS = {
    # Totals
    'Total', 'Sub Total', 'Subtotal', 'Grand Total',
    'Invoice Total', 'Total Invoice', 'Total Due', 'Total Amount Due',
    'Balance Due', 'Amount Due', 'Net Amount Due', 'New Balance',
    'Previous Balance', 'Balance Forward',
    'Current Charges', 'Total Fees', 'Total This Invoice',
    'TOTAL INVOICE CHARGE', 'Site Total',
    # Identifiers (various cases)
    'Customer Number', 'Invoice Number', 'Account Number',
    'Customer ID', 'CUSTOMER ID', 'Payment Amount',
    'Invoice Total',
    # Dates
    'Invoice Date', 'Due Date', 'Bill Date', 'Billing Date',
    'Payment Due Date', 'Service Date',
    # Account-related
    'Account Status', 'Account Balance',
    'Your Total Due', 'Your Payment Is Due',
}

# Value type patterns for validation
_DATE_RE = re.compile(
    r'^\d{1,2}[/\-]\d{1,2}[/\-]\d{2,4}$'
    r'|^\w{3,9}[\-\s]\d{1,2}[\-\s,]*\d{2,4}$'
    r'|^\d{1,2}[\-\s]\d{1,2}[\-\s]\d{2,4}$'
    r'|^(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\w*\s+\d{1,2},?\s+\d{4}$',
    re.IGNORECASE,
)
_MONEY_RE = re.compile(r'^\$?[\d,]+\.\d{2}$')
_ACCOUNT_RE = re.compile(r'^[\dA-Z][\dA-Za-z\-/. ]{2,20}$')
_ADDRESS_RE = re.compile(
    r'(?:\d+\s+\w+\s+(?:ST|AVE|RD|DR|LN|BLVD|WAY|CT|PL|PKWY|HWY|LOOP|CIR))'
    r'|(?:PO\s+BOX\s+\d+)'
    r'|(?:\b[A-Z]{2}\s+\d{5})',
    re.IGNORECASE,
)

# Labels that expect specific value types
_LABEL_EXPECTS = {
    'date': {'date', 'bill date', 'billing date', 'invoice date', 'due date',
             'payment due date', 'service date', 'your payment is due'},
    'money': {'total', 'sub total', 'subtotal', 'grand total', 'amount due',
              'balance due', 'total due', 'total amount due', 'invoice total',
              'total invoice', 'net amount due', 'new balance', 'previous balance',
              'current charges', 'total fees', 'total this invoice', 'account balance',
              'total invoice charge', 'site total', 'your total due', 'payment amount'},
    'address': {'service address', 'billing address', 'mailing address', 'site address'},
}


def _value_type_ok(label_name: str, value: str) -> bool:
    """Check if a value's format is plausible for the given label."""
    ln = label_name.lower().strip()
    v = value.strip()

    # Date labels should get date-like values
    if ln in _LABEL_EXPECTS['date']:
        # Accept dates, or words like "UPON RECEIPT", "Net 30", etc.
        if _DATE_RE.match(v) or len(v) <= 20:
            return True
        # Reject long strings, addresses
        if _ADDRESS_RE.search(v) or len(v) > 30:
            return False

    # Money labels should get money-like values
    if ln in _LABEL_EXPECTS['money']:
        if _MONEY_RE.match(v) or re.match(r'^[\d,.]+$', v):
            return True
        if len(v) > 15:
            return False

    # Address labels should NOT get short codes or numbers
    if ln in _LABEL_EXPECTS['address']:
        if len(v) < 5 or re.match(r'^\d{1,6}$', v):
            return False

    return True


def _classify_line(text: str) -> str:
    """Classify a text line as 'label', 'label_inline', 'noise', or 'value'."""
    t = text.strip()
    if not t:
        return 'noise'
    if _is_noise(t):
        return 'noise'

    # Inline label: value
    if _LABEL_INLINE_RE.match(t):
        m = _LABEL_INLINE_RE.match(t)
        label_part = m.group(1).strip()
        if len(label_part) <= 40:
            return 'label_inline'

    # Label ending with colon
    if _LABEL_COLON_RE.match(t):
        m = _LABEL_COLON_RE.match(t)
        if len(m.group(1).strip()) <= 40:
            return 'label'

    # Label ending with # (Invoice #, PO #)
    if _LABEL_HASH_RE.match(t):
        return 'label'

    # Label ending with NO. / No. (INVOICE NO., Customer No.)
    if _LABEL_NO_RE.match(t):
        return 'label'

    # Known labels (exact match, case-sensitive for specificity)
    if t in _KNOWN_LABELS:
        return 'label'

    # Case-insensitive match for known labels
    t_lower = t.lower()
    for kl in _KNOWN_LABELS:
        if t_lower == kl.lower():
            return 'label'

    return 'value'


def _extract_label_name(text: str) -> str:
    """Extract clean label name from text."""
    t = text.strip()
    m = _LABEL_COLON_RE.match(t)
    if m:
        return m.group(1).strip()
    m = _LABEL_HASH_RE.match(t)
    if m:
        return m.group(1).strip() + ' #'
    m = _LABEL_NO_RE.match(t)
    if m:
        return m.group(1).strip() + ' No.'
    return t


# ---------------------------------------------------------------------------
# Form field extraction
# ---------------------------------------------------------------------------

def _extract_form_fields(text_lines: list[str]) -> list[dict]:
    """Extract form fields by sequential text pairing with label-block grouping.

    Stops at tear line. Validates value types against label expectations.
    """
    fields = []
    n = len(text_lines)
    i = 0

    while i < n:
        text = text_lines[i].strip()

        # Stop at tear line (payment stub boundary)
        if _TEAR_LINE_RE.search(text):
            break

        cls = _classify_line(text)

        if cls == 'noise':
            i += 1
            continue

        # Inline label:value
        if cls == 'label_inline':
            m = _LABEL_INLINE_RE.match(text)
            if m:
                label_name = m.group(1).strip()
                value = m.group(2).strip()
                if label_name and value and len(label_name) <= 40:
                    if _value_type_ok(label_name, value):
                        fields.append({
                            'name': label_name,
                            'value': value,
                            'confidence': 0.90,
                        })
            i += 1
            continue

        if cls == 'label':
            # Collect consecutive labels (label-block), max 4
            label_block = []
            j = i
            while j < n and len(label_block) < 4:
                t = text_lines[j].strip()
                if _TEAR_LINE_RE.search(t):
                    break
                c = _classify_line(t)
                if c == 'label':
                    label_block.append(_extract_label_name(t))
                    j += 1
                elif c == 'label_inline':
                    # Inline breaks the block — emit it directly
                    m = _LABEL_INLINE_RE.match(t)
                    if m and _value_type_ok(m.group(1).strip(), m.group(2).strip()):
                        fields.append({
                            'name': m.group(1).strip(),
                            'value': m.group(2).strip(),
                            'confidence': 0.90,
                        })
                    j += 1
                    break
                elif c == 'noise':
                    j += 1
                    continue
                else:
                    break

            # Collect values for the label block
            value_block = []
            k = j
            while k < n and len(value_block) < len(label_block):
                t = text_lines[k].strip()
                if _TEAR_LINE_RE.search(t):
                    break
                c = _classify_line(t)
                if c == 'noise':
                    k += 1
                    continue
                if c in ('label', 'label_inline'):
                    break
                value_block.append(t)
                k += 1

            # Pair with value-type validation
            for idx, label_name in enumerate(label_block):
                if idx < len(value_block):
                    val = value_block[idx]
                    if _value_type_ok(label_name, val):
                        fields.append({
                            'name': label_name,
                            'value': val,
                            'confidence': 0.90,
                        })
                    else:
                        # Try the next value (skip mismatch)
                        # This handles cases where an address line intervenes
                        pass

            i = k
            continue

        # value line — skip
        i += 1

    return fields


# ---------------------------------------------------------------------------
# Table detection (spatial, from line-level bounding boxes)
# ---------------------------------------------------------------------------

_ROW_Y_THRESHOLD = 0.012


def _extract_spatial_lines(docai_json: dict) -> list[dict]:
    """Extract line-level text blocks with normalized bounding boxes."""
    doc = docai_json.get('document', docai_json)
    raw_text = doc.get('text', '')
    clean_text, orig_to_clean = _preprocess_text(raw_text)

    blocks = []
    for page_idx, page in enumerate(doc.get('pages', [])):
        source = page.get('lines', []) or page.get('paragraphs', []) or page.get('tokens', [])
        for item in source:
            layout = item.get('layout', {})
            text = _get_text_from_layout(layout, clean_text, orig_to_clean)
            bbox = _get_bbox_normalized(layout)
            if text and bbox:
                blocks.append({
                    'text': text,
                    'x': bbox['x'], 'y': bbox['y'],
                    'w': bbox['w'], 'h': bbox['h'],
                    'right': bbox['x'] + bbox['w'],
                    'bottom': bbox['y'] + bbox['h'],
                    'page': page_idx,
                })
    return blocks


def _detect_tables(spatial_lines: list[dict]) -> list[dict]:
    """Detect table regions from spatial line data."""
    if not spatial_lines:
        return []

    clean = [b for b in spatial_lines if b['text'].strip() and not _is_noise(b['text'])]
    sorted_lines = sorted(clean, key=lambda b: (b['page'], b['y'], b['x']))

    rows = []
    current_row = []
    current_y = -999.0
    for block in sorted_lines:
        if abs(block['y'] - current_y) < _ROW_Y_THRESHOLD:
            current_row.append(block)
        else:
            if current_row:
                rows.append(sorted(current_row, key=lambda b: b['x']))
            current_row = [block]
            current_y = block['y']
    if current_row:
        rows.append(sorted(current_row, key=lambda b: b['x']))

    multi_col = []
    for i, row in enumerate(rows):
        if len(row) >= 3:
            x_min = min(b['x'] for b in row)
            x_max = max(b['right'] for b in row)
            if (x_max - x_min) > 0.30:
                multi_col.append(i)

    if not multi_col:
        return []

    table_ranges = []
    run_start = multi_col[0]
    run_end = multi_col[0]
    for idx in multi_col[1:]:
        if idx <= run_end + 2:
            run_end = idx
        else:
            if run_end - run_start >= 1:
                table_ranges.append((run_start, run_end))
            run_start = idx
            run_end = idx
    if run_end - run_start >= 1:
        table_ranges.append((run_start, run_end))

    result = []
    for start, end in table_ranges:
        table_rows = rows[start:end + 1]
        if not table_rows:
            continue
        header_row = table_rows[0]
        header_xs = [(b['x'], b['right']) for b in header_row]
        headers = [[b['text'].strip() for b in header_row]]
        body_rows = []
        for row in table_rows[1:]:
            aligned = [''] * len(header_xs)
            for block in row:
                best_col = -1
                best_overlap = -1
                for ci, (hx_start, hx_end) in enumerate(header_xs):
                    overlap = min(block['right'], hx_end) - max(block['x'], hx_start)
                    if overlap > best_overlap:
                        best_overlap = overlap
                        best_col = ci
                if best_col >= 0:
                    if aligned[best_col]:
                        aligned[best_col] += '\n' + block['text'].strip()
                    else:
                        aligned[best_col] = block['text'].strip()
            body_rows.append(aligned)
        result.append({'headers': headers, 'rows': body_rows})

    return result


# ---------------------------------------------------------------------------
# Main extraction
# ---------------------------------------------------------------------------

def _get_avg_confidence(docai_json: dict) -> float:
    """Get average token confidence from the document."""
    doc = docai_json.get('document', docai_json)
    total = count = 0
    for page in doc.get('pages', []):
        for token in page.get('tokens', []):
            conf = token.get('layout', {}).get('confidence', 0.0)
            if conf > 0:
                total += conf
                count += 1
    return total / max(count, 1)


def extract_fields(docai_json: dict) -> dict:
    """Extract form fields and tables from Document AI JSON."""
    doc = docai_json.get('document', docai_json)
    raw_text = doc.get('text', '')
    full_text = raw_text.replace('\\n', '\n')

    text_lines = full_text.split('\n')
    form_fields = _extract_form_fields(text_lines)

    avg_conf = _get_avg_confidence(docai_json)
    for field in form_fields:
        field['confidence'] = round(avg_conf, 3)

    spatial_lines = _extract_spatial_lines(docai_json)
    tables = _detect_tables(spatial_lines)

    return {'form_fields': form_fields, 'tables': tables, 'text': full_text}


def extract_from_file(json_path: Path) -> dict:
    """Extract fields from a Document AI JSON file."""
    with open(json_path, encoding='utf-8') as f:
        docai_json = json.load(f)
    result = extract_fields(docai_json)
    result['md5'] = json_path.stem
    return result


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

def _normalize_field_name(name: str) -> str:
    return re.sub(r'[:\s#.]+', ' ', name).strip().lower()


def validate_against_gold(local_result: dict, gold_result: dict) -> dict:
    """Compare local extraction against Form Parser gold standard."""
    gold_fields = gold_result.get('form_fields', [])
    local_fields = local_result.get('form_fields', [])

    # Deduplicate by normalized name
    gold_lookup = {}
    for gf in gold_fields:
        name = _normalize_field_name(gf.get('name', ''))
        val = gf.get('value', '').strip()
        if name and val:
            gold_lookup.setdefault(name, set()).add(val)

    local_dedup = {}
    for lf in local_fields:
        name = _normalize_field_name(lf.get('name', ''))
        val = lf.get('value', '').strip()
        if name and val:
            local_dedup.setdefault(name, set()).add(val)

    name_matches = 0
    value_matches = 0

    for local_name, local_vals in local_dedup.items():
        matched_gold_name = None
        for gname in gold_lookup:
            if local_name == gname or local_name in gname or gname in local_name:
                matched_gold_name = gname
                break
        if matched_gold_name:
            name_matches += 1
            for lv in local_vals:
                lv_clean = re.sub(r'\s+', ' ', lv).strip()
                for gv in gold_lookup[matched_gold_name]:
                    gv_clean = re.sub(r'\s+', ' ', gv).strip()
                    if lv_clean == gv_clean or lv_clean in gv_clean or gv_clean in lv_clean:
                        value_matches += 1
                        break
                else:
                    continue
                break

    total_local = len(local_dedup)
    gold_dedup = len(gold_lookup)

    return {
        'gold_field_count': gold_dedup,
        'local_field_count': total_local,
        'name_matches': name_matches,
        'value_matches': value_matches,
        'name_match_rate': name_matches / max(total_local, 1),
        'value_match_rate': value_matches / max(total_local, 1),
        'gold_recall': value_matches / max(gold_dedup, 1),
        'gold_table_count': len(gold_result.get('tables', [])),
        'local_table_count': len(local_result.get('tables', [])),
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    import argparse

    parser = argparse.ArgumentParser(description='Local field extractor from Document AI OCR JSON')
    parser.add_argument('--json', type=Path, help='Single JSON file')
    parser.add_argument('--input-dir', type=Path, help='Batch input directory')
    parser.add_argument('--output-dir', type=Path, help='Batch output directory')
    parser.add_argument('--validate', action='store_true', help='Validate against gold standard')
    parser.add_argument('--gold-dir', type=Path, help='Gold standard directory')
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format='%(message)s')

    if args.json:
        result = extract_from_file(args.json)
        print(json.dumps(result, indent=2))
        return

    input_dir = args.input_dir or Path(__file__).parent / 'data' / 'feb12_json'
    json_files = sorted(f for f in input_dir.glob('*.json') if f.is_file() and not f.name.startswith('.'))

    if not json_files:
        print(f'No JSON files in {input_dir}')
        return

    if args.validate:
        gold_dir = args.gold_dir or input_dir / 'form_parser_output'
        if not gold_dir.exists():
            print(f'Gold dir not found: {gold_dir}')
            return

        print(f'Validating {len(json_files)} files against {gold_dir}')
        print('=' * 85)

        all_metrics = []
        for jf in json_files:
            gold_path = gold_dir / jf.name
            if not gold_path.exists():
                continue

            local = extract_from_file(jf)
            with open(gold_path, encoding='utf-8') as f:
                gold = json.load(f)

            m = validate_against_gold(local, gold)
            m['md5'] = jf.stem
            all_metrics.append(m)

            vmr = m['value_match_rate']
            status = 'OK' if vmr >= 0.6 else 'LOW'
            print(
                f'  {jf.stem[:12]}  '
                f'flds:{m["local_field_count"]:2d}(g{m["gold_field_count"]:2d})  '
                f'val:{m["value_matches"]:2d}/{m["local_field_count"]:2d}={vmr:.0%}  '
                f'recall:{m["gold_recall"]:.0%}  '
                f'tbl:{m["local_table_count"]}/{m["gold_table_count"]}  '
                f'[{status}]'
            )

        if all_metrics:
            print('=' * 85)
            avg_vmr = sum(m['value_match_rate'] for m in all_metrics) / len(all_metrics)
            avg_recall = sum(m['gold_recall'] for m in all_metrics) / len(all_metrics)
            total_val = sum(m['value_matches'] for m in all_metrics)
            total_local = sum(m['local_field_count'] for m in all_metrics)
            total_gold = sum(m['gold_field_count'] for m in all_metrics)
            print(f'SUMMARY ({len(all_metrics)} files):')
            print(f'  Precision (val match rate): {avg_vmr:.1%}')
            print(f'  Recall (gold coverage):     {avg_recall:.1%}')
            print(f'  Total matches:              {total_val}/{total_local} local, {total_gold} gold')
        return

    # Batch
    output_dir = args.output_dir or input_dir / 'local_extract'
    output_dir.mkdir(parents=True, exist_ok=True)
    print(f'Extracting {len(json_files)} files -> {output_dir}')
    for jf in json_files:
        result = extract_from_file(jf)
        out_path = output_dir / jf.name
        with open(out_path, 'w', encoding='utf-8') as f:
            json.dump(result, f, indent=2)
        print(f'  {jf.stem[:12]}  {len(result["form_fields"])} fields, {len(result["tables"])} tables')
    print(f'Done. Output: {output_dir}/')


if __name__ == '__main__':
    main()
