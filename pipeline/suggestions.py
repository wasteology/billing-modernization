"""
AI suggestion layer for invoice processing review.

Provides candidate values for human review — NOT extraction.
These are analysis helpers that surface likely values from OCR text
so the human doesn't have to scan raw text with their eyes.

Functions:
    suggest_vendor(raw_text) -> (candidate, source)
    suggest_account(vendor, raw_text) -> candidate or None
"""

import re
from typing import Optional

# Industry keywords that appear near business names on invoices
_INDUSTRY_KEYWORDS = re.compile(
    r'\b(?:LLC|Inc|Corp|Ltd|L\.?L\.?C|Incorporated|Corporation|Company|Co\b'
    r'|Services|Disposal|Waste|Sanitation|Recycling|Hauling|Trash'
    r'|Environmental|Dumpster|Rubbish|Refuse|Scrap|Demolition'
    r'|Roll.?Off|Carting|Collection|Clean.?Up|Removal|Container'
    r'|Metal|Shredding|Compost)\b',
    re.IGNORECASE,
)

# Names to exclude — these are the customer, not the vendor
_EXCLUDE_NAMES = re.compile(
    r'\b(?:Wasteology|UPS|JLL|Jones\s+Lang|Duke\s+Energy)\b',
    re.IGNORECASE,
)

# Business name pattern: capitalized words (2-6 words) near an industry keyword
# Captures lines like "ACME WASTE SERVICES LLC" or "Metro Disposal, Inc."
_BUSINESS_NAME_RE = re.compile(
    r'(?:^|\n)\s*'
    r'((?:[A-Z][A-Za-z\'&\-\.]+(?:\s+|,\s*)){1,5}'  # 2-6 capitalized words
    r'(?:LLC|Inc\.?|Corp\.?|Ltd\.?|L\.?L\.?C\.?|Co\.?|Company|Incorporated|Corporation)?)'
    r'\s*(?:\n|$|,)',
    re.MULTILINE,
)


def suggest_vendor(raw_text: str) -> tuple[Optional[str], str]:
    """Scan OCR text for business-name-like strings near industry keywords.

    This does NOT duplicate detect_vendor(). It extracts raw business name
    strings as a starting point for the human — the same text the human
    would scan with their eyes.

    Args:
        raw_text: Full raw OCR text from the document.

    Returns:
        (candidate_name, source) where source is 'header_scan', 'keyword_proximity',
        or 'none' if no candidate found.
    """
    if not raw_text:
        return None, 'none'

    # Work with first 2000 chars (invoice headers)
    text = raw_text[:2000]
    # Normalize literal \n from OCR storage
    text = text.replace('\\n', '\n')

    # Strategy 1: First non-trivial line that contains an industry keyword
    lines = text.split('\n')
    for line in lines[:20]:
        line_stripped = line.strip()
        if len(line_stripped) < 5 or len(line_stripped) > 80:
            continue
        if _EXCLUDE_NAMES.search(line_stripped):
            continue
        if _INDUSTRY_KEYWORDS.search(line_stripped):
            # Clean up the candidate
            candidate = _clean_candidate(line_stripped)
            if candidate and len(candidate) >= 5:
                return candidate, 'header_scan'

    # Strategy 2: Look for capitalized business name patterns near keywords
    for match in _BUSINESS_NAME_RE.finditer(text):
        candidate_raw = match.group(1).strip().rstrip(',')
        if _EXCLUDE_NAMES.search(candidate_raw):
            continue
        if len(candidate_raw) < 5 or len(candidate_raw) > 60:
            continue
        # Must have at least one industry keyword nearby (within 200 chars)
        start = max(0, match.start() - 100)
        end = min(len(text), match.end() + 100)
        context = text[start:end]
        if _INDUSTRY_KEYWORDS.search(context):
            candidate = _clean_candidate(candidate_raw)
            if candidate and len(candidate) >= 5:
                return candidate, 'keyword_proximity'

    return None, 'none'


def suggest_account(vendor: str, raw_text: str,
                    md5_hash: str = None) -> Optional[str]:
    """Find candidate account number for a vendor whose extraction failed.

    Uses the vendor's known format and examples to build a scan regex,
    then searches for values spatially associated with account-related
    keywords using Document AI bounding box data. Falls back to flat-text
    keyword zones if bounding box data unavailable.

    This is a CANDIDATE, not an extraction. confidence=suggested, never auto.
    The human confirms.

    Args:
        vendor: Detected vendor name.
        raw_text: Full raw OCR text.
        md5_hash: Document hash — used to fetch bounding box data from GCS.

    Returns:
        Candidate account number string, or None.
    """
    if not vendor or not raw_text:
        return None

    # Get format info from parsing_engines
    format_info = _get_account_format_safe(vendor)
    if not format_info or not format_info.get('has_account'):
        return None

    fmt = format_info.get('format') or ''
    examples = format_info.get('examples') or []

    # Build scan regex from examples
    scan_patterns = _examples_to_patterns(examples, fmt)
    if not scan_patterns:
        return None

    # Strategy 1: Flat-text keyword zones — sequential ordering preserves
    # label→value association better than spatial when text isn't fragmented
    text = raw_text.replace('\\n', '\n')
    zones = _extract_keyword_zones(text)
    for zone in zones:
        for pattern in scan_patterns:
            match = pattern.search(zone)
            if match:
                candidate = match.group(0).strip()
                if len(candidate) >= 3 and not re.match(r'^0+$', candidate):
                    return candidate

    # Strategy 2: Spatial bounding-box extraction — finds values near
    # account keywords using Document AI coordinates. Handles cases where
    # flat text ordering is scrambled or keywords aren't in expected sequence.
    if md5_hash:
        candidate = _suggest_account_spatial(md5_hash, scan_patterns)
        if candidate:
            return candidate

    return None


def get_account_format_display(vendor: str) -> str:
    """Get human-readable account format string for a vendor.

    Returns format like 'D-DDDD-DDDDDDD' or '' if unknown.
    """
    info = _get_account_format_safe(vendor)
    if not info:
        return ''
    return info.get('format') or ''


# =========================================================================
# Spatial bounding-box helpers
# =========================================================================

# Partial keyword fragments for spatial proximity check.
# Document AI fragments labels like "Customer Number" across blocks,
# so we check for partial matches: "ustom", "ccount", "Acct", "#:" etc.
_ACCT_KEYWORD_FRAGMENTS = re.compile(
    r'(?:account|acct|customer|ustomer|ccount|umber\s*#|#\s*:)',
    re.IGNORECASE,
)

# Spatial proximity thresholds (normalized 0-1 coords)
_SPATIAL_PROXIMITY = 0.06  # blocks within 6% of page height/width


def _suggest_account_spatial(md5_hash: str,
                             scan_patterns: list[re.Pattern]) -> Optional[str]:
    """Use Document AI bounding boxes to find account numbers near keywords.

    Value-first approach: find ALL blocks with format-matching values,
    then score by spatial proximity to account-related keyword text.
    Handles Document AI text fragmentation across block boundaries.
    """
    try:
        from .invoice_renderer import fetch_docai_json
    except ImportError:
        return None

    try:
        docai = fetch_docai_json(md5_hash)
    except Exception:
        return None

    if not docai:
        return None

    doc = docai.get('document', docai)
    raw_text = doc.get('text', '')
    if not raw_text:
        return None

    from .invoice_renderer import _preprocess_text, _get_text_from_layout, _get_bbox
    clean_text, orig_to_clean = _preprocess_text(raw_text)

    # Extract all line blocks with normalized bounding boxes
    blocks = []
    for page in doc.get('pages', []):
        for line in page.get('lines', []):
            layout = line.get('layout', {})
            text = _get_text_from_layout(layout, clean_text, orig_to_clean)
            bbox = _get_bbox(layout)
            if text and bbox:
                blocks.append({
                    'text': text,
                    'x': bbox['x'],
                    'y': bbox['y'],
                    'width': bbox['width'],
                    'height': bbox['height'],
                })

    if not blocks:
        return None

    # Identify keyword blocks (any block containing account-related fragments)
    keyword_blocks = [b for b in blocks if _ACCT_KEYWORD_FRAGMENTS.search(b['text'])]

    # Find all format-matching values across all blocks
    value_candidates = []
    for b in blocks:
        for pattern in scan_patterns:
            match = pattern.search(b['text'])
            if match:
                val = match.group(0).strip()
                if len(val) >= 3 and not re.match(r'^0+$', val):
                    value_candidates.append((val, b))

    if not value_candidates:
        return None

    # Score each value candidate by proximity to keyword blocks
    scored = []
    for val, vblock in value_candidates:
        best_dist = float('inf')
        for kw in keyword_blocks:
            # Euclidean distance between block centers (normalized coords)
            vc_x = vblock['x'] + vblock['width'] / 2
            vc_y = vblock['y'] + vblock['height'] / 2
            kc_x = kw['x'] + kw['width'] / 2
            kc_y = kw['y'] + kw['height'] / 2
            dist = ((vc_x - kc_x) ** 2 + (vc_y - kc_y) ** 2) ** 0.5
            best_dist = min(best_dist, dist)

        # Only consider values within proximity threshold of a keyword
        if best_dist < _SPATIAL_PROXIMITY:
            scored.append((best_dist, val, vblock))

    if not scored:
        # Relax: if no keyword blocks found, try values in upper 30% of page
        for val, vblock in value_candidates:
            if vblock['y'] < 0.30:
                scored.append((vblock['y'], val, vblock))

    if scored:
        scored.sort(key=lambda s: s[0])
        return scored[0][1]

    return None




def _clean_candidate(text: str) -> str:
    """Clean up a business name candidate."""
    # Strip common noise
    text = re.sub(r'\s+', ' ', text).strip()
    # Remove trailing punctuation except period after Inc./Corp.
    text = re.sub(r'[,;:\-]+$', '', text).strip()
    # Remove leading numbers (address fragments)
    text = re.sub(r'^\d+\s+', '', text).strip()
    return text


def _get_account_format_safe(vendor: str) -> Optional[dict]:
    """Safely import and call get_account_format from parsing_engines."""
    try:
        import sys
        sys.path.insert(0, '/home/scstclair/projects/parsing_engines')
        from account_number.account_extraction_engine import get_account_format
        return get_account_format(vendor)
    except (ImportError, AttributeError):
        return None


def _extract_keyword_zones(text: str, zone_size: int = 200) -> list[str]:
    """Find text zones near account-related keywords.

    Returns list of text chunks (up to zone_size chars) following each keyword.
    """
    keywords = re.compile(
        r'\b(?:Account\s*(?:#|No\.?|Number)?|Acct\s*(?:#|No\.?)?'
        r'|Customer\s*(?:#|No\.?|Number|ID)?)\s*:?\s*',
        re.IGNORECASE,
    )

    zones = []
    for match in keywords.finditer(text):
        start = match.end()
        end = min(len(text), start + zone_size)
        zone = text[start:end]
        if zone.strip():
            zones.append(zone)

    return zones


def _examples_to_patterns(examples: list[str], fmt: str) -> list[re.Pattern]:
    """Build scan regex patterns from example account numbers.

    Converts example digits to \\d, letters to [A-Z], preserves delimiters.
    Allows ±1 digit flexibility in length.
    """
    patterns = []

    for example in examples:
        if not example:
            continue
        # Build regex from example structure
        regex_parts = []
        i = 0
        while i < len(example):
            ch = example[i]
            if ch.isdigit():
                # Count consecutive digits
                j = i
                while j < len(example) and example[j].isdigit():
                    j += 1
                n = j - i
                lo = max(1, n - 1)
                hi = n + 1
                regex_parts.append(f'\\d{{{lo},{hi}}}')
                i = j
            elif ch.isalpha():
                # Count consecutive letters
                j = i
                while j < len(example) and example[j].isalpha():
                    j += 1
                n = j - i
                lo = max(1, n - 1)
                hi = n + 1
                regex_parts.append(f'[A-Za-z]{{{lo},{hi}}}')
                i = j
            elif ch in '-/. ':
                regex_parts.append(re.escape(ch))
                i += 1
            else:
                regex_parts.append(re.escape(ch))
                i += 1

        if regex_parts:
            pattern_str = ''.join(regex_parts)
            try:
                patterns.append(re.compile(pattern_str))
            except re.error:
                continue

    # Fallback: if format string looks like D-DDDD-DDDDDDD, build from that
    if not patterns and fmt:
        pattern_str = _format_to_regex(fmt)
        if pattern_str:
            try:
                patterns.append(re.compile(pattern_str))
            except re.error:
                pass

    return patterns


def _format_to_regex(fmt: str) -> Optional[str]:
    """Convert format string like 'D-DDDD-DDDDDDD' to regex."""
    if not fmt:
        return None

    parts = []
    i = 0
    while i < len(fmt):
        ch = fmt[i]
        if ch == 'D':
            j = i
            while j < len(fmt) and fmt[j] == 'D':
                j += 1
            n = j - i
            lo = max(1, n - 1)
            hi = n + 1
            parts.append(f'\\d{{{lo},{hi}}}')
            i = j
        elif ch == 'X':
            j = i
            while j < len(fmt) and fmt[j] == 'X':
                j += 1
            n = j - i
            lo = max(1, n - 1)
            hi = n + 1
            parts.append(f'[A-Za-z0-9]{{{lo},{hi}}}')
            i = j
        elif ch == 'A':
            j = i
            while j < len(fmt) and fmt[j] == 'A':
                j += 1
            n = j - i
            lo = max(1, n - 1)
            hi = n + 1
            parts.append(f'[A-Za-z]{{{lo},{hi}}}')
            i = j
        elif ch in '-/. ':
            parts.append(re.escape(ch))
            i += 1
        elif ch in '[]()':
            # Optional group markers — skip
            i += 1
        else:
            parts.append(re.escape(ch))
            i += 1

    return ''.join(parts) if parts else None
