#!/usr/bin/env python3
"""
Invoice Date Extraction Engine v2.0

Extracts invoice/statement dates from raw OCR invoice text.

CORE PRINCIPLE: VENDOR DEFINES THE INVOICE PATTERN.
Each vendor has specific date formats and locations. Vendor-specific
extraction is tried first, with generic patterns as fallback.

Usage:
    from parsing_engines.dates import extract_invoice_date, extract_invoice_month

    # NEW: Vendor-specific extraction (recommended)
    date = extract_invoice_date('Waste Connections', raw_ocr_text)

    # OLD: Generic extraction (backward compatible)
    date = extract_invoice_date(raw_ocr_text)

    month = extract_invoice_month(raw_ocr_text)  # Returns: "2025-01"
"""

import re
from typing import Optional, Dict, Any, Callable

__version__ = "2.0.0"
__author__ = "Wasteology"


# =============================================================================
# VENDOR DATE CONFIGURATIONS
# =============================================================================

VENDOR_DATES: Dict[str, Dict[str, Any]] = {}


# =============================================================================
# Date Validation Helpers
# =============================================================================

def _validate_date(month: int, day: int, year: int) -> bool:
    """Validate date components."""
    # Handle 2-digit year
    if year < 100:
        year = 2000 + year if year < 50 else 1900 + year
    # Relaxed range: 2015-2035 (was 2020-2030)
    return 1 <= month <= 12 and 1 <= day <= 31 and 2015 <= year <= 2035


def _format_date(month: int, day: int, year: int) -> str:
    """Format date components to YYYY-MM-DD."""
    # Handle 2-digit year
    if year < 100:
        year = 2000 + year if year < 50 else 1900 + year
    return f"{year}-{month:02d}-{day:02d}"


def _parse_mdy(match, validate: bool = True) -> Optional[str]:
    """Parse MM/DD/YY(YY) match groups."""
    try:
        month, day, year = int(match.group(1)), int(match.group(2)), int(match.group(3))
        if year < 100:
            year = 2000 + year if year < 50 else 1900 + year
        if not validate or _validate_date(month, day, year):
            return _format_date(month, day, year)
    except (ValueError, TypeError):
        pass
    return None


# =============================================================================
# Generic Date Patterns (Fallback)
# =============================================================================

# Patterns are tuples of (regex_pattern, date_format)
# date_format: 'MDY' = MM/DD/YYYY, 'YMD' = YYYY-MM-DD, 'MONTH' = Month DD, YYYY
# Order matters: most specific/reliable patterns first

DATE_PATTERNS = [
    # === Invoice Date / Bill Date patterns (most reliable) ===
    # Invoice Date: 01/15/2025 or Invoice Date: 01-15-2025
    (r'(?:Invoice\s*Date|Inv\.?\s*Date)[:\s]+(\d{1,2})[/\-](\d{1,2})[/\-](\d{4})', 'MDY'),
    (r'(?:Invoice\s*Date|Inv\.?\s*Date)[:\s]+(\d{1,2})[/\-](\d{1,2})[/\-](\d{2})', 'MDY'),
    # Statement Date: 01/15/2025
    (r'(?:Statement\s*Date|Stmt\.?\s*Date)[:\s]+(\d{1,2})[/\-](\d{1,2})[/\-](\d{4})', 'MDY'),
    (r'(?:Statement\s*Date|Stmt\.?\s*Date)[:\s]+(\d{1,2})[/\-](\d{1,2})[/\-](\d{2})', 'MDY'),
    # Bill Date: 01/15/2025
    (r'(?:Bill\s*Date|Bill\.?\s*Date|Billing\s*Date)[:\s]+(\d{1,2})[/\-](\d{1,2})[/\-](\d{4})', 'MDY'),
    (r'(?:Bill\s*Date|Bill\.?\s*Date|Billing\s*Date)[:\s]+(\d{1,2})[/\-](\d{1,2})[/\-](\d{2})', 'MDY'),

    # === Generic Date: patterns ===
    (r'\bDate[:\s]+(\d{1,2})[/\-](\d{1,2})[/\-](\d{4})', 'MDY'),
    (r'\bDate[:\s]+(\d{1,2})[/\-](\d{1,2})[/\-](\d{2})', 'MDY'),

    # === Month name patterns ===
    # Invoice Date: January 15, 2025
    (r'(?:Invoice\s*Date|Inv\.?\s*Date)[:\s]+([A-Za-z]+)\s+(\d{1,2}),?\s*(\d{4})', 'MONTH'),
    # Date: January 15, 2025
    (r'\bDate[:\s]+([A-Za-z]+)\s+(\d{1,2}),?\s*(\d{4})', 'MONTH'),

    # === Service period (use first date) ===
    (r'(?:Service\s*Period|Period)[:\s]+(\d{1,2})[/\-](\d{1,2})[/\-](\d{4})', 'MDY'),
    (r'(?:Service\s*Period|Period)[:\s]+(\d{1,2})[/\-](\d{1,2})[/\-](\d{2})', 'MDY'),

    # === ISO format: 2025-01-15 ===
    (r'(?:Invoice\s*Date|Date)[:\s]+(\d{4})-(\d{2})-(\d{2})', 'YMD'),

    # === OCR artifact tolerant patterns ===
    (r'(?:InvoiceDate|InvDate)[:\s]+(\d{1,2})[/\-](\d{1,2})[/\-](\d{4})', 'MDY'),
    (r'(?:StatementDate|StmtDate)[:\s]+(\d{1,2})[/\-](\d{1,2})[/\-](\d{4})', 'MDY'),

    # === Multiline patterns (date on next line) ===
    (r'(?:Invoice\s*Date|Inv\.?\s*Date)\s*\n\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{4})', 'MDY'),
    (r'(?:Invoice\s*Date|Inv\.?\s*Date)\s*\n\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2})', 'MDY'),
    (r'(?:Statement\s*Date|Stmt\.?\s*Date)\s*\n\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{4})', 'MDY'),
    (r'(?:Statement\s*Date|Stmt\.?\s*Date)\s*\n\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2})', 'MDY'),
]

# Month name to number mapping
MONTH_MAP = {
    'january': '01', 'february': '02', 'march': '03', 'april': '04',
    'may': '05', 'june': '06', 'july': '07', 'august': '08',
    'september': '09', 'october': '10', 'november': '11', 'december': '12',
    'jan': '01', 'feb': '02', 'mar': '03', 'apr': '04',
    'jun': '06', 'jul': '07', 'aug': '08', 'sep': '09',
    'oct': '10', 'nov': '11', 'dec': '12'
}


# =============================================================================
# Text Normalization
# =============================================================================

def normalize_ocr_text(raw_text: str) -> str:
    """
    Normalize OCR text to handle common artifacts.

    Handles:
    - Literal '\\n' strings -> actual newlines (common in OCR CSV exports)
    - Extra whitespace

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
    text = text.replace('\\n', '\n')

    # Normalize whitespace within lines (but preserve newlines)
    lines = text.split('\n')
    lines = [re.sub(r'[ \t]+', ' ', line) for line in lines]
    text = '\n'.join(lines)

    return text


# =============================================================================
# Generic Date Extraction (Fallback)
# =============================================================================

def _extract_generic_date(text: str) -> Optional[str]:
    """
    Extract date using generic patterns.

    This is the fallback when no vendor-specific extractor exists.

    Args:
        text: Normalized OCR text

    Returns:
        Date in YYYY-MM-DD format, or None
    """
    for pattern, date_format in DATE_PATTERNS:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            try:
                if date_format == 'MDY':
                    month, day, year = match.groups()
                    # Handle 2-digit year
                    if len(year) == 2:
                        year = '20' + year if int(year) < 50 else '19' + year
                    # Validate
                    month_int = int(month)
                    day_int = int(day)
                    year_int = int(year)
                    if _validate_date(month_int, day_int, year_int):
                        return _format_date(month_int, day_int, year_int)

                elif date_format == 'YMD':
                    year, month, day = match.groups()
                    year_int = int(year)
                    month_int = int(month)
                    day_int = int(day)
                    if _validate_date(month_int, day_int, year_int):
                        return _format_date(month_int, day_int, year_int)

                elif date_format == 'MONTH':
                    month_name, day, year = match.groups()
                    month = MONTH_MAP.get(month_name.lower()[:3])
                    if month:
                        day_int = int(day)
                        year_int = int(year)
                        if _validate_date(int(month), day_int, year_int):
                            return f"{year_int}-{month}-{day_int:02d}"

            except (ValueError, KeyError, TypeError):
                continue

    return None


# =============================================================================
# Main Extraction Functions
# =============================================================================

def extract_invoice_date(vendor_name_or_text, text: Optional[str] = None) -> Optional[str]:
    """
    Extract invoice date from raw OCR text.

    Supports both old and new signatures for backward compatibility:
    - OLD: extract_invoice_date(text)
    - NEW: extract_invoice_date(vendor_name, text)

    The new signature enables vendor-specific extraction which is more accurate.

    Args:
        vendor_name_or_text: Either vendor name (str) when using new signature,
                            or OCR text (str) when using old signature
        text: OCR text when using new signature, None for old signature

    Returns:
        Date in YYYY-MM-DD format, or None if not found
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

    # Normalize OCR text
    normalized = normalize_ocr_text(raw_text)

    if not normalized:
        return None

    # Try vendor-specific extractor first
    if vendor_name and vendor_name in VENDOR_DATES:
        config = VENDOR_DATES[vendor_name]
        if 'extract' in config and config['extract']:
            result = config['extract'](normalized)
            if result:
                return result

    # Fallback to generic patterns
    return _extract_generic_date(normalized)


def extract_invoice_month(raw_text: str, vendor_name: Optional[str] = None) -> Optional[str]:
    """
    Extract invoice month from raw OCR text.

    Args:
        raw_text: Raw OCR text from invoice
        vendor_name: Optional vendor name for vendor-specific extraction

    Returns:
        Month in YYYY-MM format, or None if not found
    """
    if vendor_name:
        date = extract_invoice_date(vendor_name, raw_text)
    else:
        date = extract_invoice_date(raw_text)

    if date:
        return date[:7]  # YYYY-MM
    return None


# =============================================================================
# Utility Functions
# =============================================================================

def get_pattern_count() -> int:
    """Return the number of generic extraction patterns."""
    return len(DATE_PATTERNS)


def get_configured_vendors() -> list:
    """Return list of vendors with specific date extractors."""
    return list(VENDOR_DATES.keys())


def get_vendor_date_format(vendor_name: str) -> Optional[str]:
    """Return the expected date format for a vendor."""
    if vendor_name in VENDOR_DATES:
        return VENDOR_DATES[vendor_name].get('format')
    return None


def test_extraction(sample_text: str, vendor_name: Optional[str] = None, verbose: bool = True) -> Optional[str]:
    """
    Test extraction on sample text with optional verbose output.

    Args:
        sample_text: OCR text to test
        vendor_name: Optional vendor for vendor-specific extraction
        verbose: If True, print which pattern matched

    Returns:
        Extracted date or None
    """
    if not sample_text:
        return None

    text = normalize_ocr_text(sample_text)

    # Try vendor-specific first
    if vendor_name and vendor_name in VENDOR_DATES:
        config = VENDOR_DATES[vendor_name]
        if 'extract' in config and config['extract']:
            result = config['extract'](text)
            if result:
                if verbose:
                    print(f"Vendor-specific extractor for '{vendor_name}' matched")
                    print(f"  Format: {config.get('format', 'unknown')}")
                    print(f"  Extracted: {result}")
                return result
            elif verbose:
                print(f"Vendor-specific extractor for '{vendor_name}' found no match")

    # Try generic patterns
    for i, (pattern, date_format) in enumerate(DATE_PATTERNS):
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            try:
                if date_format == 'MDY':
                    month, day, year = match.groups()
                    if len(year) == 2:
                        year = '20' + year if int(year) < 50 else '19' + year
                    month_int, day_int, year_int = int(month), int(day), int(year)
                    if _validate_date(month_int, day_int, year_int):
                        result = _format_date(month_int, day_int, year_int)
                        if verbose:
                            print(f"Generic pattern {i} matched: {pattern[:50]}...")
                            print(f"  Extracted: {result}")
                        return result

                elif date_format == 'YMD':
                    year, month, day = match.groups()
                    year_int, month_int, day_int = int(year), int(month), int(day)
                    if _validate_date(month_int, day_int, year_int):
                        result = _format_date(month_int, day_int, year_int)
                        if verbose:
                            print(f"Generic pattern {i} matched: {pattern[:50]}...")
                            print(f"  Extracted: {result}")
                        return result

                elif date_format == 'MONTH':
                    month_name, day, year = match.groups()
                    month = MONTH_MAP.get(month_name.lower()[:3])
                    if month:
                        day_int, year_int = int(day), int(year)
                        if _validate_date(int(month), day_int, year_int):
                            result = f"{year_int}-{month}-{day_int:02d}"
                            if verbose:
                                print(f"Generic pattern {i} matched: {pattern[:50]}...")
                                print(f"  Extracted: {result}")
                            return result

            except (ValueError, KeyError, TypeError):
                continue

    if verbose:
        print("No pattern matched")
    return None


# =============================================================================
# Import Vendor Additions
# =============================================================================

try:
    from .date_extraction_additions import VENDOR_DATE_ADDITIONS
    VENDOR_DATES.update(VENDOR_DATE_ADDITIONS)
except ImportError:
    try:
        from date_extraction_additions import VENDOR_DATE_ADDITIONS
        VENDOR_DATES.update(VENDOR_DATE_ADDITIONS)
    except ImportError:
        pass  # No additions file yet

# NG Report fixes (must be AFTER main additions to override)
try:
    from .date_extraction_ng_fixes import VENDOR_DATE_NG_FIXES
    VENDOR_DATES.update(VENDOR_DATE_NG_FIXES)
except ImportError:
    try:
        from date_extraction_ng_fixes import VENDOR_DATE_NG_FIXES
        VENDOR_DATES.update(VENDOR_DATE_NG_FIXES)
    except ImportError:
        pass


# =============================================================================
# CLI for Testing
# =============================================================================

if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1:
        # Check for vendor flag
        vendor = None
        args = sys.argv[1:]
        if args[0] == '--vendor' and len(args) >= 3:
            vendor = args[1]
            test_text = " ".join(args[2:])
        else:
            test_text = " ".join(args)

        result = test_extraction(test_text, vendor_name=vendor, verbose=True)
        if result:
            print(f"\nResult: {result}")
        else:
            print("\nNo date found")
    else:
        # Show usage
        print("Invoice Date Extraction Engine v2.0")
        print(f"Generic Patterns: {get_pattern_count()}")
        print(f"Configured Vendors: {len(VENDOR_DATES)}")
        if VENDOR_DATES:
            print(f"  {', '.join(list(VENDOR_DATES.keys())[:5])}...")
        print("\nUsage:")
        print('  python date_extraction_engine.py <text>')
        print('  python date_extraction_engine.py --vendor "Waste Connections" <text>')
        print("\nExample:")
        print('  python date_extraction_engine.py "Invoice Date: 01/15/2025"')
