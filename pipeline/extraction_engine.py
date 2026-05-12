"""
DB-driven ExtractionEngine — loads patterns from ip_vendor_pattern, executes in priority order.

Supports scan_type execution modes:
  INLINE           — re.search on full text
  FORWARD_COLUMNAR — find label line, scan N lines forward for value
  REVERSE_COLUMNAR — find label line, scan N lines backward for value
  WIDE_COLUMNAR    — same as FORWARD but with wider scan window (used for address blocks)

Multi-match mode (execution_mode='MULTI'):
  Used for charge_line_item extraction (step 8). Runs re.finditer across full text,
  returning N charge items per document instead of a single value.
"""

import json
import logging
import re
from typing import Optional

import psycopg2.extras

from .database import get_connection

log = logging.getLogger(__name__)


# =============================================================================
# Charge sanitization — ported from parsing_engines/charge_code/unified.py
# =============================================================================

_GARBAGE_PATTERNS = [
    re.compile(r'[ween]{3,}\s+[ween]{3,}', re.IGNORECASE),
    re.compile(r'^\d{3}[-.)]\s*\d{3,4}'),
    re.compile(r'Location\s+Charges\s*$', re.MULTILINE),
    re.compile(r'^FRCH\s*$', re.MULTILINE),
    re.compile(r'P\.?O\.?\s*Box', re.IGNORECASE),
    re.compile(r'^[A-Z][a-z]+\s+\d{3}[-.)]\d{3}'),
    re.compile(r'^(?:Amount|Balance|Current|Total|Net)\s+(?:Due|Charges?|Amount)\s*$', re.IGNORECASE),
    re.compile(r'^(?:Invoice|Sub)\s*Total\s*$', re.IGNORECASE),
    re.compile(r'^\d+\s+[A-Z][A-Za-z]+\s+(?:St|Ave|Rd|Blvd|Dr|Way|Ct|Pl|Ln|Pkwy|Hwy)\b'),
    re.compile(r'^[A-Z]{2}\s+\d{5}(?:-\d{4})?\s*$'),
    re.compile(r'^\d+\s*$'),
    re.compile(r'^-?\d[\d,]*\.?\d*\s*$'),  # bare number/amount (e.g. "95.06")
    re.compile(r'^PER\s+[A-Z][A-Z\s]+$'),
]


def _is_garbage(desc: str) -> bool:
    """Return True if description is OCR garble, address, summary total, etc."""
    if not desc or len(desc.strip()) < 3:
        return True
    first_line = desc.strip().split('\n')[0].strip()
    for pat in _GARBAGE_PATTERNS:
        if pat.search(first_line):
            return True
    collapsed = ' '.join(desc.split())
    for pat in _GARBAGE_PATTERNS:
        if pat.search(collapsed):
            return True
    return False


def _sanitize_description(desc: str) -> str:
    """Clean up a charge description: strip trailing refs, normalize whitespace."""
    desc = re.sub(r'\s*\n\s*', ' ', desc).strip()
    desc = re.sub(r'\s+\d{6,}\s+\d{6,}\s*$', '', desc)
    desc = re.sub(r'\s+\d{7,}\s*$', '', desc)
    return desc.strip()


def _clean_amount(val: str) -> Optional[float]:
    """Parse amount string: strip $, commas, handle parens/trailing dash for negatives."""
    if not val:
        return None
    if re.match(r'^-?\$?\d+,\d{2}$', val.strip()):
        val = val.replace(',', '.')
    cleaned = re.sub(r'[$,\s]', '', val)
    if cleaned.endswith('-') or cleaned.startswith('('):
        cleaned = '-' + cleaned.replace('-', '').replace('(', '').replace(')', '')
    try:
        v = float(cleaned)
        return v if abs(v) < 1_000_000 else None
    except ValueError:
        return None


def _clean_qty(val: str) -> Optional[float]:
    """Parse quantity string."""
    if not val:
        return None
    cleaned = re.sub(r'[,\s]', '', val)
    try:
        return float(cleaned)
    except ValueError:
        return None

# =============================================================================
# Field label anchors — used to find the label line for columnar scans
# =============================================================================

_FIELD_LABELS = {
    'account_number': [
        re.compile(r'ACCOUNT\s*(?:#|NUMBER|NO\.?)', re.IGNORECASE),
        re.compile(r'CUSTOMER\s*(?:#|ID|NUMBER|NO\.?)', re.IGNORECASE),
        re.compile(r'ACCT\s*(?:#|NO\.?)', re.IGNORECASE),
    ],
    'invoice_number': [
        re.compile(r'INVOICE\s*(?:#|NUMBER|NO\.?)', re.IGNORECASE),
        re.compile(r'BILL\s*(?:#|NUMBER|NO\.?)', re.IGNORECASE),
    ],
    'invoice_date': [
        re.compile(r'(?:INVOICE|BILL(?:ING)?|SERVICE)\s*DATE', re.IGNORECASE),
        re.compile(r'^\s*DATE\s*$', re.IGNORECASE),
    ],
    'amount_due': [
        re.compile(r'(?:AMOUNT|BALANCE|TOTAL)\s*DUE', re.IGNORECASE),
        re.compile(r'TOTAL\s*(?:CHARGES|AMOUNT)', re.IGNORECASE),
        re.compile(r'PLEASE\s*PAY', re.IGNORECASE),
    ],
    'vendor_detection': [],
}

# Generic value patterns per field — used when a label-only pattern matches
_FIELD_VALUE_PATTERNS = {
    'invoice_date': re.compile(
        r'(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})'
        r'|([A-Za-z]+)\s+(\d{1,2}),?\s*(\d{4})'
        r'|(\d{1,2})[-\s]([A-Za-z]{3,9})[-\s,]*(\d{4})',
    ),
    'amount_due': re.compile(
        r'\$?\s*(\d{1,3}(?:,\d{3})*\.\d{2})',
    ),
}

# Map field to step number
_FIELD_STEP = {
    'ocr_status': 1, 'document_type': 1,
    'detected_vendor': 2, 'vendor_detection': 2,
    'account_number': 3, 'hauler_account_number': 3,
    'invoice_number': 4, 'hauler_invoice_number': 4,
    'invoice_date': 5,
    'amount_due': 6, 'bill_total': 6,
}


def _build_flags(flags_str: str) -> int:
    """Convert flag string (e.g., 'IGNORECASE|DOTALL') to re flags."""
    if not flags_str or flags_str == 'NONE':
        return 0
    flags = 0
    for part in flags_str.split('|'):
        part = part.strip()
        if hasattr(re, part):
            flags |= getattr(re, part)
    return flags


def _normalize_value(text: str, method: str) -> str:
    """Apply normalization to extracted or input text."""
    if not text:
        return text
    if method == 'STRIP_WHITESPACE':
        return re.sub(r'\s+', '', text)
    if method == 'STRIP_SPACES':
        return re.sub(r'\s+', ' ', text).strip()
    if method == 'UPPERCASE':
        return text.upper()
    return text


class ExtractionEngine:
    """DB-driven pattern execution engine.

    Loads active patterns from ip_vendor_pattern, caches them by (vendor_name, field),
    and executes in priority order for a given vendor and field.
    """

    def __init__(self):
        self._cache: dict[tuple[str, str], list[dict]] = {}
        self._loaded = False

    def load_patterns(self, vendor_slug: str = None, field: str = None):
        """Load active patterns from ip_vendor_pattern into cache.

        Pre-compiles regexes and parses capture_map JSON so per-doc execution
        is pure matching with zero compilation overhead.

        Args:
            vendor_slug: Filter to specific vendor (optional)
            field: Filter to specific field (optional)
        """
        conn = get_connection()
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

        sql = """
            SELECT vendor_pattern_id, vendor_name, field, format_variant,
                   pattern_type, priority, regex_pattern, regex_flags,
                   capture_group, normalization, scan_type, scan_lines,
                   date_format, is_no_account,
                   execution_mode, capture_map, pattern_tier,
                   activation_condition, description_template
            FROM ip_vendor_pattern
            WHERE is_active = TRUE
        """
        params = []
        if vendor_slug:
            sql += " AND vendor_name = %s"
            params.append(vendor_slug)
        if field:
            sql += " AND field = %s"
            params.append(field)

        sql += " ORDER BY vendor_name, field, format_variant, priority"
        cur.execute(sql, params)

        for row in cur.fetchall():
            p = dict(row)

            # Pre-compile regex
            flags = _build_flags(p.get('regex_flags'))
            try:
                p['_compiled_regex'] = re.compile(p['regex_pattern'], flags)
            except re.error as e:
                log.warning("Skipping pattern %s (regex error): %s",
                            p.get('vendor_pattern_id'), e)
                continue

            # Pre-parse capture_map from JSONB/string to dict
            cm = p.get('capture_map')
            if isinstance(cm, str):
                try:
                    p['capture_map'] = json.loads(cm)
                except (json.JSONDecodeError, TypeError):
                    p['capture_map'] = {}
            elif cm is None:
                p['capture_map'] = {}

            # Pre-compute activation condition lowercase
            cond = p.get('activation_condition')
            p['_activation_lower'] = cond.lower() if cond else None

            key = (p['vendor_name'], p['field'])
            self._cache.setdefault(key, []).append(p)

        conn.close()
        self._loaded = True

        # Pre-build tier groups for charge_line_item patterns
        self._charge_tiers: dict[str, dict[str, list[dict]]] = {}
        for (vendor, fld), pats in self._cache.items():
            if fld == 'charge_line_item':
                tiers: dict[str, list[dict]] = {'TIER_1': [], 'TIER_2': [], 'TIER_FALLBACK': []}
                for p in pats:
                    tier = p.get('pattern_tier') or 'TIER_1'
                    tiers.setdefault(tier, []).append(p)
                self._charge_tiers[vendor] = tiers

        total = sum(len(v) for v in self._cache.values())
        log.info("ExtractionEngine loaded %d patterns for %d vendor+field combinations",
                 total, len(self._cache))

    def invalidate_cache(self):
        """Clear pattern cache. Called after pattern deploy."""
        self._cache.clear()
        self._loaded = False

    def get_patterns(self, vendor: str, field: str) -> list[dict]:
        """Get cached patterns for a vendor+field combination."""
        if not self._loaded:
            self.load_patterns()
        return self._cache.get((vendor, field), [])

    def extract(self, vendor: str, field: str,
                raw_text: str) -> tuple[Optional[str], Optional[int]]:
        """Extract a field value from raw OCR text for a given vendor.

        Returns:
            (value, pattern_id) on success
            ('NO_ACCOUNT', None) if vendor is confirmed no-account for this field
            (None, None) if no match
        """
        if not self._loaded:
            self.load_patterns()

        patterns = self._cache.get((vendor, field), [])
        if not patterns:
            return None, None

        # Check if vendor is confirmed NO_ACCOUNT for this field
        if any(p['is_no_account'] for p in patterns):
            return 'NO_ACCOUNT', None

        # Prepare text and lines for columnar scans
        # Normalize OCR text: literal \n → actual newlines
        text = raw_text.replace('\\n', '\n') if raw_text else ''
        lines = text.split('\n')

        for pattern in patterns:
            value = self._execute_pattern(pattern, field, text, lines)
            if value is not None:
                # Apply normalization
                norm = pattern.get('normalization', 'NONE')
                value = _normalize_value(value, norm)
                if value:
                    return value, pattern['vendor_pattern_id']

        return None, None

    def _execute_pattern(self, pattern: dict, field: str,
                         full_text: str, lines: list[str]) -> Optional[str]:
        """Execute a single pattern based on its scan_type."""
        scan_type = pattern.get('scan_type', 'INLINE')

        if scan_type == 'INLINE':
            return self._scan_inline(pattern, full_text)
        elif scan_type == 'FORWARD_COLUMNAR':
            return self._scan_forward(pattern, field, lines)
        elif scan_type == 'WIDE_COLUMNAR':
            return self._scan_forward(pattern, field, lines)
        elif scan_type == 'REVERSE_COLUMNAR':
            return self._scan_reverse(pattern, field, lines)
        else:
            log.warning("Unknown scan_type '%s' for pattern %s, falling back to INLINE",
                        scan_type, pattern.get('vendor_pattern_id'))
            return self._scan_inline(pattern, full_text)

    def _scan_inline(self, pattern: dict, full_text: str) -> Optional[str]:
        """INLINE: re.search on full text using pre-compiled regex."""
        capture = pattern.get('capture_group', 0)
        regex = pattern.get('_compiled_regex')
        if not regex:
            return None

        match = regex.search(full_text)
        if match:
            try:
                val = match.group(capture)
                return val.strip() if val else None
            except IndexError:
                return match.group(0).strip()
        return None

    def _scan_forward(self, pattern: dict, field: str,
                      lines: list[str]) -> Optional[str]:
        """FORWARD_COLUMNAR / WIDE_COLUMNAR: find label, scan N lines forward."""
        scan_lines = pattern.get('scan_lines', 3)
        capture = pattern.get('capture_group', 0)
        regex = pattern.get('_compiled_regex')
        if not regex:
            return None

        # Strategy 1: Try regex on each line. If it matches with a useful capture,
        # return the value. If it matches as a label-only (capture==0), scan forward.
        for i, line in enumerate(lines):
            stripped = line.strip()
            if not stripped:
                continue

            m = regex.search(stripped)
            if m:
                # Got a match — check if we have a useful captured value
                try:
                    val = m.group(capture)
                except IndexError:
                    val = m.group(0)

                if capture > 0 and val and val.strip():
                    # Label+value pattern matched with a captured value
                    return val.strip()

                # Label-only match (capture==0 or no value in capture group)
                # Scan forward for field-appropriate value
                value = self._scan_window_for_value(
                    field, lines, i + 1, i + 1 + scan_lines, regex, capture
                )
                if value:
                    return value

        # Strategy 2: Find label anchor for this field, then apply regex to scan window
        label_patterns = _FIELD_LABELS.get(field, [])
        for i, line in enumerate(lines):
            stripped = line.strip()
            for lp in label_patterns:
                if lp.search(stripped):
                    # Found label at line i, scan forward
                    for j in range(i + 1, min(i + 1 + scan_lines, len(lines))):
                        scan_line = lines[j].strip()
                        if not scan_line:
                            continue
                        m = regex.search(scan_line)
                        if m:
                            try:
                                val = m.group(capture)
                            except IndexError:
                                val = m.group(0)
                            if val and val.strip():
                                return val.strip()
                    break  # Only use the first label match

        return None

    def _scan_reverse(self, pattern: dict, field: str,
                      lines: list[str]) -> Optional[str]:
        """REVERSE_COLUMNAR: find label, scan N lines backward for value."""
        scan_lines = pattern.get('scan_lines', 3)
        capture = pattern.get('capture_group', 0)
        regex = pattern.get('_compiled_regex')
        if not regex:
            return None

        # Find label anchor, then scan backward
        label_patterns = _FIELD_LABELS.get(field, [])

        # Also check if the regex itself is a label pattern
        for i, line in enumerate(lines):
            stripped = line.strip()
            is_label = False

            # Check if this line matches a field label
            for lp in label_patterns:
                if lp.search(stripped):
                    is_label = True
                    break

            # Also check if the regex matches this line as a label (capture==0)
            if not is_label:
                m = regex.search(stripped)
                if m and capture == 0:
                    is_label = True

            if is_label:
                # Scan backward from line i
                start = max(0, i - scan_lines)
                for j in range(i - 1, start - 1, -1):
                    scan_line = lines[j].strip()
                    if not scan_line:
                        continue
                    m = regex.search(scan_line)
                    if m:
                        try:
                            val = m.group(capture)
                        except IndexError:
                            val = m.group(0)
                        if val and val.strip():
                            return val.strip()

                    # Try generic field value pattern as fallback
                    value = self._try_field_value(field, scan_line)
                    if value:
                        return value

        return None

    def _scan_window_for_value(self, field: str, lines: list[str],
                               start: int, end: int,
                               regex: re.Pattern, capture: int) -> Optional[str]:
        """Scan a window of lines for a value, using both the pattern regex and
        generic field value patterns."""
        end = min(end, len(lines))

        for j in range(start, end):
            scan_line = lines[j].strip()
            if not scan_line:
                continue

            # Try the pattern regex first
            m = regex.search(scan_line)
            if m:
                try:
                    val = m.group(capture) if capture > 0 else m.group(0)
                except IndexError:
                    val = m.group(0)
                if val and val.strip():
                    return val.strip()

            # Try generic field value pattern
            value = self._try_field_value(field, scan_line)
            if value:
                return value

        return None

    def _try_field_value(self, field: str, text: str) -> Optional[str]:
        """Try to extract a value using the generic field value pattern."""
        pattern = _FIELD_VALUE_PATTERNS.get(field)
        if not pattern:
            return None
        m = pattern.search(text)
        if m:
            # Return the first non-None group
            for g in m.groups():
                if g:
                    return m.group(0).strip()
        return None

    # =================================================================
    # Multi-match charge extraction (step 8)
    # =================================================================

    def extract_charges(self, vendor: str, raw_text: str) -> list[dict]:
        """Multi-match extraction for charge line items.

        Uses pre-built tier groups and pre-compiled regexes for speed.

        Returns list of dicts:
            {charge_description, amount, qty, unit_price, raw_text, vendor_pattern_id}
        """
        if not self._loaded:
            self.load_patterns()

        tiers = self._charge_tiers.get(vendor)
        if not tiers:
            return []

        # Normalize OCR text
        text = raw_text.replace('\\n', '\n') if raw_text else ''
        text_lower = text.lower()

        results = []
        seen_descs: set[str] = set()

        # TIER_1: primary patterns, all run cumulatively
        for p in tiers.get('TIER_1', []):
            cond = p.get('_activation_lower')
            if cond and cond not in text_lower:
                continue
            items = self._execute_multi_pattern(p, text)
            for item in items:
                key = (item.get('charge_description') or '').upper().strip()
                if key and key not in seen_descs:
                    seen_descs.add(key)
                    results.append(item)

        # TIER_2: secondary (fees, credits), deduped against TIER_1
        for p in tiers.get('TIER_2', []):
            cond = p.get('_activation_lower')
            if cond and cond not in text_lower:
                continue
            items = self._execute_multi_pattern(p, text)
            for item in items:
                key = (item.get('charge_description') or '').upper().strip()
                if key and key not in seen_descs:
                    seen_descs.add(key)
                    results.append(item)

        # TIER_FALLBACK: only runs if TIER_1 + TIER_2 produced nothing
        if not results:
            for p in tiers.get('TIER_FALLBACK', []):
                cond = p.get('_activation_lower')
                if cond and cond not in text_lower:
                    continue
                items = self._execute_multi_pattern(p, text)
                for item in items:
                    key = (item.get('charge_description') or '').upper().strip()
                    if key and key not in seen_descs:
                        seen_descs.add(key)
                        results.append(item)

        # Sanitize: remove garbage descriptions
        sanitized = []
        for item in results:
            desc = item.get('charge_description') or ''
            if _is_garbage(desc):
                continue
            item['charge_description'] = _sanitize_description(desc)
            if item['charge_description']:
                sanitized.append(item)

        return sanitized

    def _execute_multi_pattern(self, pattern: dict, full_text: str) -> list[dict]:
        """Run finditer using pre-compiled regex, map via pre-parsed capture_map."""
        capture_map = pattern.get('capture_map') or {}
        template = pattern.get('description_template')
        pid = pattern.get('vendor_pattern_id')
        regex = pattern.get('_compiled_regex')
        if not regex:
            return []

        items = []
        for match in regex.finditer(full_text):
            item = {
                'charge_description': None,
                'amount': None,
                'qty': None,
                'unit_price': None,
                'raw_text': match.group(0)[:500],
                'vendor_pattern_id': pid,
            }

            # Extract fields via capture_map: {regex_group → output_field}
            groups = {}
            for group_name, output_field in capture_map.items():
                try:
                    val = match.group(group_name)
                except (IndexError, re.error):
                    val = None
                if val:
                    groups[group_name] = val.strip()
                    # Map to output fields
                    if output_field == 'charge_description':
                        item['charge_description'] = val.strip()
                    elif output_field == 'amount':
                        item['amount'] = _clean_amount(val)
                    elif output_field == 'qty':
                        item['qty'] = _clean_qty(val)
                    elif output_field == 'unit_price':
                        item['unit_price'] = _clean_amount(val)

            # Apply description_template if provided
            if template and groups:
                try:
                    item['charge_description'] = template.format(**groups)
                except KeyError:
                    pass  # Template references a group that didn't match

            # If no capture_map, fall back to capture_group integer
            if not capture_map:
                capture = pattern.get('capture_group', 0)
                try:
                    val = match.group(capture)
                    if val:
                        item['charge_description'] = val.strip()
                except (IndexError, re.error):
                    item['charge_description'] = match.group(0).strip()

            # Skip items with no description and no amount
            if not item.get('charge_description') and item.get('amount') is None:
                continue

            items.append(item)

        return items
