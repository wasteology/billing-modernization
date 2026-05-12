"""
Invoice Date Extraction Module v2.5

Extracts invoice/statement dates from raw OCR invoice text.

CORE PRINCIPLE: VENDOR DEFINES THE INVOICE PATTERN.
Use vendor-specific extraction for best results.

Coverage: 240 vendors with specific patterns (Feb 2026)

Usage:
    from parsing_engines.dates import extract_invoice_date, extract_invoice_month

    # Vendor-specific extraction (recommended)
    date = extract_invoice_date('Waste Connections', raw_ocr_text)

    # Generic extraction (backward compatible)
    date = extract_invoice_date(raw_ocr_text)

    month = extract_invoice_month(raw_ocr_text)  # Returns: "2025-01"

    # Check configured vendors
    from parsing_engines.dates import VENDOR_DATES, get_configured_vendors
    print(get_configured_vendors())  # Returns list of 240 vendors
"""

from .date_extraction_engine import (
    extract_invoice_date,
    extract_invoice_month,
    normalize_ocr_text,
    get_pattern_count,
    get_configured_vendors,
    get_vendor_date_format,
    test_extraction,
    DATE_PATTERNS,
    MONTH_MAP,
    VENDOR_DATES,
)

__all__ = [
    'extract_invoice_date',
    'extract_invoice_month',
    'normalize_ocr_text',
    'get_pattern_count',
    'get_configured_vendors',
    'get_vendor_date_format',
    'test_extraction',
    'DATE_PATTERNS',
    'MONTH_MAP',
    'VENDOR_DATES',
]
