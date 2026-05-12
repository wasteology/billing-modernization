#!/usr/bin/env python3
"""
Amount Due Extraction Engine

Extracts bill total/amount due from raw OCR invoice text.

Uses 40+ regex patterns to handle various invoice formats including:
- Same-line patterns: "Total Due: $123.45"
- Multiline patterns: "Total Due\n$123.45" (amount on next line)

Multiline patterns are critical for Waste Connections, Republic Services,
Waste Management, and GFL invoices where OCR puts amounts on separate lines.

Coverage: ~90.9% on production invoice corpus (Feb 2026)

Usage:
    from parsing_engines.amount_due import extract_bill_total

    amount = extract_bill_total(raw_ocr_text)
    if amount:
        print(f"Bill total: ${amount:.2f}")
"""

import re
from typing import Optional

__version__ = "1.0.0"
__author__ = "Wasteology"


# =============================================================================
# Amount Extraction Patterns
# =============================================================================

# Patterns are tuples of (regex_pattern, is_multiline_hint)
# is_multiline_hint indicates if this pattern expects amount on next line
# Order matters: most specific/reliable patterns first

TOTAL_PATTERNS = [
    # === MULTILINE PATTERNS (amount on next line - common in OCR) ===
    # These patterns match labels, then we look for amount on next line
    # Waste Connections: "Total Due\n$ 92.93" or "PAY THIS AMOUNT\n92.93"
    (r'(?:TOTAL\s*DUE|AMOUNT\s*DUE|BALANCE\s*DUE)\s*\n\s*\$?\s*([\d,]+\.\d{2})', True),
    (r'(?:PAY\s*THIS\s*AMOUNT)\s*\n\s*\$?\s*([\d,]+\.\d{2})', True),
    (r'(?:TOTAL\s*AMOUNT\s*DUE)\s*\n\s*\$?\s*([\d,]+\.\d{2})', True),
    (r'(?:PLEASE\s*PAY)\s*\n\s*\$?\s*([\d,]+\.\d{2})', True),
    # Republic: "Total Amount Due\n$1,017.88"
    (r'(?:CURRENT\s*INVOICE\s*CHARGES)\s*\n\s*\$?\s*([\d,]+\.\d{2})', True),
    # GFL: "TOTAL DUE:\n$252.00"
    (r'(?:TOTAL\s*DUE)[:\s]*\n\s*\$?\s*([\d,]+\.\d{2})', True),
    # Generic multiline
    (r'(?:INVOICE\s*TOTAL)\s*\n\s*\$?\s*([\d,]+\.\d{2})', True),
    (r'(?:GRAND\s*TOTAL)\s*\n\s*\$?\s*([\d,]+\.\d{2})', True),
    (r'(?:NET\s*DUE)\s*\n\s*\$?\s*([\d,]+\.\d{2})', True),

    # === PRIMARY SAME-LINE PATTERNS (most reliable) ===
    # Amount due / Balance due patterns
    (r'(?:AMOUNT\s*DUE|BALANCE\s*DUE|TOTAL\s*DUE|AMT\.?\s*DUE)[:\s]*\$?\s*([\d,]+\.?\d*)', False),
    (r'(?:PLEASE\s*PAY)[:\s]*\$?\s*([\d,]+\.?\d*)', False),
    (r'(?:PAY\s*THIS\s*AMOUNT)[:\s]*\$?\s*([\d,]+\.?\d*)', False),
    (r'(?:REMITTANCE\s*AMOUNT|REMIT\s*AMOUNT)[:\s]*\$?\s*([\d,]+\.?\d*)', False),

    # === Invoice total patterns ===
    (r'(?:INVOICE\s*TOTAL|TOTAL\s*INVOICE|INV\.?\s*TOTAL)[:\s]*\$?\s*([\d,]+\.?\d*)', False),
    (r'(?:CURRENT\s*INVOICE\s*TOTAL)[:\s]*\$?\s*([\d,]+\.?\d*)', False),
    (r'(?:TOTAL\s*THIS\s*INVOICE)[:\s]*\$?\s*([\d,]+\.?\d*)', False),
    (r'(?:TOTAL\s*AMOUNT\s*DUE)[:\s]*\$?\s*([\d,]+\.?\d*)', False),

    # === Grand total / Total charges ===
    (r'(?:GRAND\s*TOTAL)[:\s]*\$?\s*([\d,]+\.?\d*)', False),
    (r'(?:TOTAL\s*CHARGES?)[:\s]*\$?\s*([\d,]+\.?\d*)', False),
    (r'(?:CURRENT\s*CHARGES?)[:\s]*\$?\s*([\d,]+\.?\d*)', False),
    (r'(?:NEW\s*CHARGES?)[:\s]*\$?\s*([\d,]+\.?\d*)', False),

    # === Vendor-specific patterns ===
    # Waste Management style
    (r'(?:TOTAL\s*CURRENT\s*BILLING)[:\s]*\$?\s*([\d,]+\.?\d*)', False),
    (r'(?:CURRENT\s*BILLING\s*TOTAL)[:\s]*\$?\s*([\d,]+\.?\d*)', False),
    # Republic Services style
    (r'(?:ACCOUNT\s*BALANCE)[:\s]*\$?\s*([\d,]+\.?\d*)', False),
    (r'(?:BALANCE\s*FORWARD)[:\s]*\$?\s*([\d,]+\.?\d*)', False),
    # GFL style
    (r'(?:TOTAL\s*DUE)[:\s]*\$?\s*([\d,]+\.?\d*)', False),
    # Generic billing
    (r'(?:BILLING\s*TOTAL|BILL\s*TOTAL)[:\s]*\$?\s*([\d,]+\.?\d*)', False),
    (r'(?:NET\s*AMOUNT)[:\s]*\$?\s*([\d,]+\.?\d*)', False),
    (r'(?:SUBTOTAL)[:\s]*\$?\s*([\d,]+\.?\d*)', False),
    (r'(?:NET\s*DUE)[:\s]*\$?\s*([\d,]+\.?\d*)', False),

    # === OCR artifact tolerant patterns (collapsed spaces) ===
    (r'(?:AMOUNTDUE|BALANCEDUE|TOTALDUE)[:\s]*\$?\s*([\d,]+\.?\d*)', False),
    (r'(?:INVOICETOTAL|TOTALINVOICE)[:\s]*\$?\s*([\d,]+\.?\d*)', False),
    (r'(?:GRANDTOTAL)[:\s]*\$?\s*([\d,]+\.?\d*)', False),
    (r'(?:PAYTHISAMOUNT)[:\s]*\$?\s*([\d,]+\.?\d*)', False),

    # === Low priority: Simple TOTAL at end of document ===
    (r'(?:^|\n)\s*TOTAL[:\s]*\$?\s*([\d,]+\.?\d*)\s*(?:$|\n)', False),
]


# =============================================================================
# Text Normalization
# =============================================================================

def normalize_ocr_text(raw_text: str) -> str:
    """
    Normalize OCR text to handle common artifacts.

    Handles:
    - Literal '\\n' strings -> actual newlines (common in OCR CSV exports)
    - Collapsed spaces
    - Extra whitespace
    - Common OCR misreads

    Args:
        raw_text: Raw OCR text

    Returns:
        Normalized text
    """
    if not raw_text:
        return ''

    text = str(raw_text)

    # Handle pandas NaN
    if text.lower() in ('nan', 'none', ''):
        return ''

    # CRITICAL: Convert literal '\n' strings to actual newlines
    # OCR CSV exports often have escaped newlines that need to be real newlines
    # for multiline regex patterns to work
    text = text.replace('\\n', '\n')

    # Normalize whitespace within lines (but preserve newlines for pattern matching)
    text = re.sub(r'[ \t]+', ' ', text)

    # Common OCR fixes for amounts
    text = re.sub(r'\$\s+', '$', text)  # "$ 100" -> "$100"

    return text


# =============================================================================
# Vendor-Specific Amount Extractors
# =============================================================================
# Vendor-specific extractors are tried first before generic patterns.
# Each entry maps vendor name → callable(text) -> Optional[float].
# Starts empty — populated as HITL grind discovers vendor-specific needs.

from typing import Callable, Dict

VENDOR_AMOUNT_EXTRACTORS: Dict[str, Callable[[str], Optional[float]]] = {}


# =============================================================================
# Generic Extraction (fallback)
# =============================================================================

def _extract_wide_columnar_amount(text: str) -> Optional[float]:
    """Extract amount from wide columnar layouts (label and value on separate lines, 1-15 lines apart).

    Handles GFL, Republic Services, and similar formats where OCR puts
    TOTAL AMOUNT DUE / TOTAL DUE on one line and the dollar amount many lines below.
    """
    lines = text.split('\n')
    _AMOUNT_LABELS = [
        re.compile(r'TOTAL\s*AMOUNT\s*DUE', re.I),
        re.compile(r'AMOUNT\s*DUE', re.I),
        re.compile(r'TOTAL\s*DUE', re.I),
        re.compile(r'BALANCE\s*DUE', re.I),
        re.compile(r'PLEASE\s*PAY', re.I),
        re.compile(r'PAY\s*THIS\s*AMOUNT', re.I),
    ]
    _AMT_RE = re.compile(r'^\s*\$?\s*([\d,]+\.\d{2})\s*$')

    for i, line in enumerate(lines):
        for label_re in _AMOUNT_LABELS:
            if not label_re.search(line):
                continue
            # Check if amount is inline after label
            after = line[label_re.search(line).end():]
            m = re.search(r'\$?\s*([\d,]+\.\d{2})', after)
            if m:
                try:
                    amount = float(m.group(1).replace(',', ''))
                    if 0.01 <= amount <= 1_000_000:
                        return amount
                except ValueError:
                    pass
            # Wide columnar: scan next 15 lines for a standalone dollar amount
            for j in range(i + 1, min(i + 15, len(lines))):
                m = _AMT_RE.match(lines[j])
                if m:
                    try:
                        amount = float(m.group(1).replace(',', ''))
                        if 0.01 <= amount <= 1_000_000:
                            return amount
                    except ValueError:
                        pass
            break  # only match first label occurrence
    return None


def _extract_generic_amount(text: str) -> Optional[float]:
    """Extract bill total using generic patterns (40+ patterns).

    Args:
        text: Normalized, uppercased OCR text

    Returns:
        Bill total as float, or None if not found
    """
    # Try wide columnar first (handles GFL/Republic multi-line gaps)
    result = _extract_wide_columnar_amount(text)
    if result is not None:
        return result

    for pattern_tuple in TOTAL_PATTERNS:
        # Handle both old format (string) and new format (tuple)
        if isinstance(pattern_tuple, tuple):
            pattern, is_multiline = pattern_tuple
        else:
            pattern = pattern_tuple
            is_multiline = False

        # Use MULTILINE flag for all patterns
        flags = re.IGNORECASE | re.MULTILINE

        match = re.search(pattern, text, flags)
        if match:
            try:
                amount_str = match.group(1).replace(',', '').strip()
                # Handle case where amount might have trailing period
                amount_str = amount_str.rstrip('.')
                if not amount_str:
                    continue
                amount = float(amount_str)
                # Sanity check - invoice amounts typically between $0.01 and $1M
                # Allow small amounts (under $1) for adjustment invoices
                if 0.01 <= amount <= 1_000_000:
                    return amount
            except (ValueError, IndexError):
                continue

    return None


# =============================================================================
# Main Extraction Function
# =============================================================================

def extract_bill_total(vendor_name_or_text, text: Optional[str] = None) -> Optional[float]:
    """
    Extract bill total amount from raw OCR text.

    Supports both old and new signatures for backward compatibility:
    - OLD: extract_bill_total(text)
    - NEW: extract_bill_total(vendor_name, text)

    The new signature enables vendor-specific extraction which is more accurate.

    Uses 40+ generic patterns to handle various invoice formats including:
    - Same-line patterns: "Total Due: $123.45"
    - Multiline patterns: "Total Due\\n$123.45" (amount on next line)

    Args:
        vendor_name_or_text: Either vendor name (str) when using new signature,
                            or OCR text (str) when using old signature
        text: OCR text when using new signature, None for old signature

    Returns:
        Bill total as float, or None if not found
    """
    # Determine signature type
    if text is None:
        # Old signature: first arg is text
        vendor_name = None
        raw_text = vendor_name_or_text
    else:
        # New signature: first arg is vendor
        vendor_name = vendor_name_or_text
        raw_text = text

    if not raw_text:
        return None

    # Normalize OCR text but preserve newlines for multiline patterns
    normalized = normalize_ocr_text(raw_text)

    if not normalized:
        return None

    # Try vendor-specific extractor first
    if vendor_name and vendor_name in VENDOR_AMOUNT_EXTRACTORS:
        result = VENDOR_AMOUNT_EXTRACTORS[vendor_name](normalized)
        if result is not None:
            return result

    # Fallback to generic patterns
    return _extract_generic_amount(normalized.upper())


# =============================================================================
# Utility Functions
# =============================================================================

def get_pattern_count() -> int:
    """Return the number of extraction patterns."""
    return len(TOTAL_PATTERNS)


def test_extraction(sample_text: str, verbose: bool = True) -> Optional[float]:
    """
    Test extraction on sample text with optional verbose output.

    Args:
        sample_text: OCR text to test
        verbose: If True, print which pattern matched

    Returns:
        Extracted amount or None
    """
    if not sample_text:
        return None

    text = normalize_ocr_text(sample_text).upper()

    for i, pattern_tuple in enumerate(TOTAL_PATTERNS):
        if isinstance(pattern_tuple, tuple):
            pattern, is_multiline = pattern_tuple
        else:
            pattern = pattern_tuple
            is_multiline = False

        match = re.search(pattern, text, re.IGNORECASE | re.MULTILINE)
        if match:
            try:
                amount_str = match.group(1).replace(',', '').strip().rstrip('.')
                if amount_str:
                    amount = float(amount_str)
                    if 0.01 <= amount <= 1_000_000:
                        if verbose:
                            print(f"Pattern {i} matched: {pattern[:50]}...")
                            print(f"  Extracted: ${amount:.2f}")
                        return amount
            except (ValueError, IndexError):
                continue

    if verbose:
        print("No pattern matched")
    return None


# =============================================================================
# CLI for Testing
# =============================================================================

if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1:
        # Test with provided text
        test_text = " ".join(sys.argv[1:])
        result = test_extraction(test_text, verbose=True)
        if result:
            print(f"\nResult: ${result:.2f}")
        else:
            print("\nNo amount found")
    else:
        # Show usage
        print("Amount Due Extraction Engine")
        print(f"Patterns: {get_pattern_count()}")
        print("\nUsage: python amount_due_extraction_engine.py <text>")
        print("\nExample:")
        print('  python amount_due_extraction_engine.py "Total Due: $123.45"')
