"""
Amount Due Extraction Module

Extracts bill total/amount due from raw OCR invoice text.

Usage:
    from parsing_engines.amount_due import extract_bill_total

    amount = extract_bill_total(raw_ocr_text)
"""

from .amount_due_extraction_engine import (
    extract_bill_total,
    normalize_ocr_text,
    get_pattern_count,
    test_extraction,
    TOTAL_PATTERNS,
    VENDOR_AMOUNT_EXTRACTORS,
)

__all__ = [
    'extract_bill_total',
    'normalize_ocr_text',
    'get_pattern_count',
    'test_extraction',
    'TOTAL_PATTERNS',
    'VENDOR_AMOUNT_EXTRACTORS',
]
