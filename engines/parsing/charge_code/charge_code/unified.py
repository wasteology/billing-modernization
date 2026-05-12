"""
Unified charge extraction with 3-tier fallback.

Tier 1: charge_code engine (45 vendor-specific extractors)
Tier 2: legacy vendor-specific extractors (charge_description/)
Tier 3: generic line item extractor (charge_description/)

Post-extraction: sanitize to remove OCR noise, headers, addresses.
"""

import re
import sys
from typing import List

from .models import ChargeItem
from .charge_code_engine import extract_charges

# Legacy extractors live outside the package tree
sys.path.insert(0, '/home/scstclair/projects/parsing_engines/charge_description')
from line_item_extraction_configured import extract_line_item_charges  # noqa: E402
from generic_line_item_extraction import extract_generic_line_items  # noqa: E402

# Vendors with legacy configured extractors (charge_description/)
_LEGACY_CONFIGURED_VENDORS = [
    'waste connections', 'anytime', 'republic', 'waste management', 'gfl',
    'rumpke', 'waste pro', 'cockey', 'universal waste', 'robinson',
    'standard waste', 'hamilton', 'active waste', 'casella', 'boren',
    'priority waste', 'aspen', 'meridian', 'best cleaner', 'frontier',
    'fcc', 'smarttrash', 'fusion', 'lrs', 'coastal',
    'flood', 'alaska', 'eagle', 'papillion', 'ware',
]

# ── Garbage patterns that indicate non-charge text ──
_GARBAGE_PATTERNS = [
    # OCR garble: runs of e/w/n/dashes (WM invoice headers)
    re.compile(r'[ween]{3,}\s+[ween]{3,}', re.IGNORECASE),
    # Phone number AS the description start
    re.compile(r'^\d{3}[-.)]\s*\d{3,4}'),
    # WM "Location Charges" header
    re.compile(r'Location\s+Charges\s*$', re.MULTILINE),
    # WM location code as sole content
    re.compile(r'^FRCH\s*$', re.MULTILINE),
    # P.O. Box address
    re.compile(r'P\.?O\.?\s*Box', re.IGNORECASE),
    # Person name + phone (contact info, not a charge)
    re.compile(r'^[A-Z][a-z]+\s+\d{3}[-.)]\d{3}'),
    # Summary totals (not real line items)
    re.compile(r'^(?:Amount|Balance|Current|Total|Net)\s+(?:Due|Charges?|Amount)\s*$', re.IGNORECASE),
    re.compile(r'^(?:Invoice|Sub)\s*Total\s*$', re.IGNORECASE),
    # Street addresses (number + street name + suffix)
    re.compile(r'^\d+\s+[A-Z][A-Za-z]+\s+(?:St|Ave|Rd|Blvd|Dr|Way|Ct|Pl|Ln|Pkwy|Hwy)\b'),
    # State + ZIP (full line is just an address fragment)
    re.compile(r'^[A-Z]{2}\s+\d{5}(?:-\d{4})?\s*$'),
    # Just a bare number
    re.compile(r'^\d+\s*$'),
    # "PER <NAME>" (authorization note, not a charge)
    re.compile(r'^PER\s+[A-Z][A-Z\s]+$'),
]


def _is_garbage(desc: str) -> bool:
    """Return True if description is OCR noise, not a real charge."""
    if not desc or len(desc.strip()) < 3:
        return True
    # Check each line individually — garbage on ANY line that isn't accompanied
    # by real content is still garbage
    first_line = desc.split('\n')[0].strip()
    if not first_line:
        return True
    for pat in _GARBAGE_PATTERNS:
        if pat.search(first_line):
            return True
    # Multiline descriptions where ALL lines are garbage
    if '\n' in desc:
        lines = [l.strip() for l in desc.split('\n') if l.strip()]
        if all(any(p.search(l) for p in _GARBAGE_PATTERNS) for l in lines):
            return True
    # Also check the full collapsed form (catches "Disposal Co. P.O. Box")
    flat = ' '.join(desc.split())
    for pat in _GARBAGE_PATTERNS:
        if pat.search(flat):
            return True
    return False


def _sanitize_description(desc: str) -> str:
    """Clean up a charge description: strip trailing reference numbers, normalize whitespace."""
    # Collapse internal newlines to single space (charge is one logical line)
    desc = re.sub(r'\s*\n\s*', ' ', desc).strip()
    # Strip trailing work-order / account reference numbers (e.g. "DISPOSAL 2306184 5300131302")
    desc = re.sub(r'\s+\d{6,}\s+\d{6,}\s*$', '', desc)
    desc = re.sub(r'\s+\d{7,}\s*$', '', desc)
    return desc.strip()


def _sanitize_charges(items: List[ChargeItem]) -> List[ChargeItem]:
    """Filter out garbage descriptions and clean up the rest."""
    clean = []
    for item in items:
        if not item.charge_description:
            continue
        # Check raw (multiline) form first, then sanitized form
        if _is_garbage(item.charge_description):
            continue
        item.charge_description = _sanitize_description(item.charge_description)
        if _is_garbage(item.charge_description):
            continue
        if item.charge_description:
            clean.append(item)
    return clean


def _lineitem_to_chargeitem(item) -> ChargeItem:
    """Convert a legacy LineItem to ChargeItem."""
    return ChargeItem(
        charge_description=item.description,
        amount=getattr(item, 'amount', None),
        qty=getattr(item, 'qty', None),
        unit_price=getattr(item, 'unit_price', None),
        raw_text=getattr(item, 'raw_text', None),
    )


def extract_all_charges(vendor: str, ocr_text: str) -> List[ChargeItem]:
    """
    Extract charge line items using 3-tier fallback.

    Tier 1: charge_code engine (45 vendor extractors)
    Tier 2: legacy vendor-specific extractors (30 vendors)
    Tier 3: generic line item extractor

    Post-extraction: sanitize to strip OCR noise, headers, addresses.

    Returns List[ChargeItem], empty list if nothing found.
    """
    if not ocr_text or not vendor:
        return []

    # Tier 1: charge_code engine
    items = extract_charges(vendor, ocr_text)
    if items:
        return _sanitize_charges(items)

    # Tier 2: legacy vendor-specific extractors
    vendor_lower = vendor.lower().strip()
    if any(p in vendor_lower for p in _LEGACY_CONFIGURED_VENDORS):
        legacy = extract_line_item_charges(vendor, ocr_text) or []
        if legacy:
            converted = [_lineitem_to_chargeitem(li) for li in legacy if li.description]
            return _sanitize_charges(converted)

    # Tier 3: generic extractor
    generic = extract_generic_line_items(ocr_text) or []
    if generic:
        converted = [_lineitem_to_chargeitem(li) for li in generic if li.description]
        return _sanitize_charges(converted)

    return []
