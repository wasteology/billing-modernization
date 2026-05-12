#!/usr/bin/env python3
"""
Date Extraction Additions - Vendor-Specific Patterns

CORE PRINCIPLE: VENDOR DEFINES THE INVOICE PATTERN.

Each vendor has their own invoice format. This file contains vendor-specific
date extraction functions that handle the unique layouts of major vendors.

To integrate: This file is auto-imported by date_extraction_engine.py

Coverage: 398 vendors with specific patterns (34 tranches)
Extraction Rate: 74.0% (up from 61% after major vendor fixes)

Pattern types handled:
- Columnar headers (INVOICE DATE on line above value)
- Reverse columnar (value appears BEFORE label)
- Inline patterns (Invoice Date: MM/DD/YYYY)
- NavuSoft format (DATE header, Month DD, YYYY value)
- TrashBilling format (Weekday Mon DD, YYYY)
- Various date formats: MM/DD/YY, MM/DD/YYYY, Mon-DD-YY, DD-Mon-YYYY

Major vendors:
- Waste Connections, Republic Services, Waste Management
- GFL, Rumpke, Casella, Meridian Waste, Waste Pro
- 190 additional regional/local haulers

Note: All columnar patterns use _normalize_text() to handle literal \\n in OCR text

Maintained by: Wasteology
Last updated: February 2026
"""

import re
from typing import Optional


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def _normalize_text(text: str) -> str:
    """Normalize OCR text by converting literal \\n to actual newlines."""
    return text.replace('\\n', '\n')


def _validate_date(month: int, day: int, year: int) -> bool:
    """Validate date components."""
    if year < 100:
        year = 2000 + year if year < 50 else 1900 + year
    return 1 <= month <= 12 and 1 <= day <= 31 and 2015 <= year <= 2035


def _format_date(month: int, day: int, year: int) -> str:
    """Format date to YYYY-MM-DD."""
    if year < 100:
        year = 2000 + year if year < 50 else 1900 + year
    return f"{year}-{month:02d}-{day:02d}"


def _parse_date_match(match, format_type: str = 'MDY') -> Optional[str]:
    """Parse regex match groups into date string."""
    try:
        if format_type == 'MDY':
            month, day, year = int(match.group(1)), int(match.group(2)), int(match.group(3))
        elif format_type == 'YMD':
            year, month, day = int(match.group(1)), int(match.group(2)), int(match.group(3))
        else:
            return None

        if year < 100:
            year = 2000 + year if year < 50 else 1900 + year

        if _validate_date(month, day, year):
            return _format_date(month, day, year)
    except (ValueError, TypeError, IndexError):
        pass
    return None


MONTH_MAP = {
    'january': 1, 'february': 2, 'march': 3, 'april': 4,
    'may': 5, 'june': 6, 'july': 7, 'august': 8,
    'september': 9, 'october': 10, 'november': 11, 'december': 12,
    'jan': 1, 'feb': 2, 'mar': 3, 'apr': 4,
    'jun': 6, 'jul': 7, 'aug': 8, 'sep': 9,
    'oct': 10, 'nov': 11, 'dec': 12
}


# =============================================================================
# WASTE CONNECTIONS
# =============================================================================

def _extract_waste_connections_date(text: str) -> Optional[str]:
    """
    Waste Connections date extraction.

    Format: STATEMENT DATE in columnar header block
    OCR typically shows:
        STATEMENT DATE
        DUE DATE
        ACCOUNT NUMBER
        01/15/26
        02/01/26
        12345678

    The date appears several lines after STATEMENT DATE header.
    Also handles inline format: STATEMENT DATE: 01/15/26
    """
    text = _normalize_text(text)
    lines = text.split('\n')

    # Pattern 1: Columnar - find STATEMENT DATE header, date is 1-6 lines later
    for i, line in enumerate(lines):
        if 'STATEMENT DATE' in line.upper() or 'STATEMENT DT' in line.upper():
            # Check next 6 lines for a date
            for j in range(i + 1, min(i + 7, len(lines))):
                # Look for MM/DD/YY or MM/DD/YYYY at start of line
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    result = _parse_date_match(m, 'MDY')
                    if result:
                        return result

    # Pattern 2: Inline STATEMENT DATE: 01/15/26
    m = re.search(r'STATEMENT\s*DATE[:\s]+(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})', text, re.I)
    if m:
        result = _parse_date_match(m, 'MDY')
        if result:
            return result

    # Pattern 3: STMT DATE (abbreviated)
    m = re.search(r'STMT\s*DATE[:\s]+(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})', text, re.I)
    if m:
        result = _parse_date_match(m, 'MDY')
        if result:
            return result

    return None


# =============================================================================
# REPUBLIC SERVICES
# =============================================================================

def _extract_republic_date(text: str) -> Optional[str]:
    """
    Republic Services date extraction.

    Format: Invoice Date often on separate line from label
    Common OCR patterns:
        Invoice Date
        01/15/2025

        Invoice Date
        December 31, 2024

        Invoice Date: 01/15/2025

        INVOICE DATE    ACCOUNT NUMBER    DUE DATE
        01/15/2025      123456789         02/01/2025
    """
    text = _normalize_text(text)
    lines = text.split('\n')

    # Pattern 1: Multiline - Invoice Date followed by date on next lines
    for i, line in enumerate(lines):
        if re.search(r'INVOICE\s*DATE', line, re.I):
            # Check if current line has date inline (MM/DD/YYYY)
            m = re.search(r'INVOICE\s*DATE[:\s]+(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})', line, re.I)
            if m:
                result = _parse_date_match(m, 'MDY')
                if result:
                    return result

            # Check next several lines for date value (wide spacing on some invoices)
            for j in range(i + 1, min(i + 12, len(lines))):
                next_line = lines[j].strip()
                # Try MM/DD/YYYY format
                m = re.match(r'^(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})$', next_line)
                if m:
                    result = _parse_date_match(m, 'MDY')
                    if result:
                        return result
                # Try Month DD, YYYY format (e.g., December 31, 2024)
                m = re.match(r'^([A-Za-z]+)\s+(\d{1,2}),?\s*(\d{4})$', next_line)
                if m:
                    month = MONTH_MAP.get(m.group(1).lower()[:3])
                    if month:
                        day, year = int(m.group(2)), int(m.group(3))
                        if _validate_date(month, day, year):
                            return _format_date(month, day, year)

    # Pattern 2: Inline format
    m = re.search(r'INVOICE\s*DATE[:\s]+(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})', text, re.I)
    if m:
        result = _parse_date_match(m, 'MDY')
        if result:
            return result

    # Pattern 3: Bill Date as fallback
    m = re.search(r'BILL\s*DATE[:\s]+(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})', text, re.I)
    if m:
        result = _parse_date_match(m, 'MDY')
        if result:
            return result

    return None


# =============================================================================
# WASTE MANAGEMENT
# =============================================================================

def _extract_waste_management_date(text: str) -> Optional[str]:
    """
    Waste Management date extraction.

    Multiple formats:
        Invoice Date: January 15, 2025
        Invoice Date: 01/15/2025
        Bill Date: 01/15/25
        Service Period: 01/01/2025 - 01/31/2025 (use first date)
        DATE 12/18/2025 (inline, plain DATE label)
        DATE
        05/19/2025 (columnar, plain DATE label)
    """
    text = _normalize_text(text)
    lines = text.split('\n')

    # Pattern 1: Columnar - INVOICE DETAIL header with DATE on its own line
    # This is the most common WM format
    for i, line in enumerate(lines):
        stripped = line.strip().upper()
        if stripped == 'DATE':
            # Check next few lines for date value
            for j in range(i + 1, min(i + 3, len(lines))):
                next_line = lines[j].strip()
                m = re.match(r'^(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})$', next_line)
                if m:
                    result = _parse_date_match(m, 'MDY')
                    if result:
                        return result
        # Pattern 2: Inline - DATE followed by date on same line
        if stripped.startswith('DATE ') and not 'SERVICE' in stripped:
            m = re.match(r'^DATE\s+(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})', stripped)
            if m:
                result = _parse_date_match(m, 'MDY')
                if result:
                    return result

    # Pattern 3: Invoice Date with month name
    m = re.search(r'INVOICE\s*DATE[:\s]+([A-Za-z]+)\s+(\d{1,2}),?\s*(\d{4})', text, re.I)
    if m:
        month_name = m.group(1).lower()[:3]
        month = MONTH_MAP.get(month_name)
        if month:
            day, year = int(m.group(2)), int(m.group(3))
            if _validate_date(month, day, year):
                return _format_date(month, day, year)

    # Pattern 4: Invoice Date numeric
    m = re.search(r'INVOICE\s*DATE[:\s]+(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})', text, re.I)
    if m:
        result = _parse_date_match(m, 'MDY')
        if result:
            return result

    # Pattern 5: Bill Date
    m = re.search(r'BILL\s*DATE[:\s]+(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})', text, re.I)
    if m:
        result = _parse_date_match(m, 'MDY')
        if result:
            return result

    # Pattern 6: Billing Date
    m = re.search(r'BILLING\s*DATE[:\s]+(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})', text, re.I)
    if m:
        result = _parse_date_match(m, 'MDY')
        if result:
            return result

    # Pattern 7: Service Period (use first date)
    m = re.search(r'SERVICE\s*PERIOD[:\s]+(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})', text, re.I)
    if m:
        result = _parse_date_match(m, 'MDY')
        if result:
            return result

    # Pattern 8: Multiline Invoice Date
    for i, line in enumerate(lines):
        if re.search(r'INVOICE\s*DATE', line, re.I) and i + 1 < len(lines):
            next_line = lines[i + 1].strip()
            m = re.match(r'^(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})', next_line)
            if m:
                result = _parse_date_match(m, 'MDY')
                if result:
                    return result

    return None


# =============================================================================
# GFL
# =============================================================================

def _extract_gfl_date(text: str) -> Optional[str]:
    """
    GFL date extraction.

    Format: INVOICE DATE in header block
    Common patterns:
        INVOICE DATE:           (wide columnar, value 3-8 lines below)
        12/31/2024

        INVOICE DATE: 12/31/2024  (inline)

        DATE                    (bare label, DD-Mon-YYYY on next line)
        31-Aug-2025

        12/31/2024              (reverse columnar — value ABOVE label)
        INVOICE DATE:
    """
    text = _normalize_text(text)
    lines = text.split('\n')

    # DD-Mon-YYYY regex (31-Aug-2025, 20-Feb-2026)
    _DD_MON_RE = re.compile(r'(\d{1,2})[-\s](Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\w*[-\s,]*(\d{4})', re.I)

    # Pattern 1: INVOICE DATE label — inline, forward columnar, or DD-Mon-YYYY
    for i, line in enumerate(lines):
        if re.search(r'INVOICE\s*DATE', line, re.I):
            # Inline numeric
            m = re.search(r'INVOICE\s*DATE[:\s]+(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})', line, re.I)
            if m:
                result = _parse_date_match(m, 'MDY')
                if result:
                    return result

            # Forward columnar (value 1-15 lines below label — GFL puts up to 11 lines of headers between)
            for j in range(i + 1, min(i + 15, len(lines))):
                ln = lines[j].strip()
                # Numeric MM/DD/YYYY (exact line or start of line with trailing amount)
                m = re.match(r'^(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})', ln)
                if m:
                    result = _parse_date_match(m, 'MDY')
                    if result:
                        return result
                # DD-Mon-YYYY
                m = _DD_MON_RE.match(ln)
                if m:
                    day, mon, year = int(m.group(1)), MONTH_MAP.get(m.group(2).lower()[:3]), int(m.group(3))
                    if mon and _validate_date(mon, day, year):
                        return _format_date(mon, day, year)

            # Reverse columnar (value 1-5 lines ABOVE label)
            for j in range(max(0, i - 5), i):
                ln = lines[j].strip()
                m = re.match(r'^(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})$', ln)
                if m:
                    result = _parse_date_match(m, 'MDY')
                    if result:
                        return result
                m = _DD_MON_RE.match(ln)
                if m:
                    day, mon, year = int(m.group(1)), MONTH_MAP.get(m.group(2).lower()[:3]), int(m.group(3))
                    if mon and _validate_date(mon, day, year):
                        return _format_date(mon, day, year)

    # Pattern 2: Bare DATE label — forward columnar with DD-Mon-YYYY or numeric
    for i, line in enumerate(lines):
        if re.match(r'^\s*DATE\s*$', line, re.I):
            for j in range(i + 1, min(i + 10, len(lines))):
                ln = lines[j].strip()
                m = re.match(r'^(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})$', ln)
                if m:
                    result = _parse_date_match(m, 'MDY')
                    if result:
                        return result
                m = _DD_MON_RE.match(ln)
                if m:
                    day, mon, year = int(m.group(1)), MONTH_MAP.get(m.group(2).lower()[:3]), int(m.group(3))
                    if mon and _validate_date(mon, day, year):
                        return _format_date(mon, day, year)

    # Pattern 3: Inline DATE: with numeric
    m = re.search(r'\bDATE[:\s]+(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})', text, re.I)
    if m:
        result = _parse_date_match(m, 'MDY')
        if result:
            return result

    return None


# =============================================================================
# RUMPKE
# =============================================================================

def _extract_rumpke_date(text: str) -> Optional[str]:
    """
    Rumpke date extraction.

    Format: Date on first line with page info
    Common patterns:
        Date: 09/03/25 Page 1 of 1
        Date: 04/02/25 Page 1 of 1
        Invoice Date: 01/15/25
    """
    text = _normalize_text(text)

    # Pattern 1: Date: MM/DD/YY Page X of Y (most common Rumpke format)
    m = re.search(r'Date:\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s+Page', text, re.I)
    if m:
        result = _parse_date_match(m, 'MDY')
        if result:
            return result

    # Pattern 2: Simple Date: MM/DD/YY inline
    m = re.search(r'\bDate:\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})', text, re.I)
    if m:
        result = _parse_date_match(m, 'MDY')
        if result:
            return result

    # Pattern 3: Invoice Date inline
    m = re.search(r'INVOICE\s*DATE[:\s]+(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})', text, re.I)
    if m:
        result = _parse_date_match(m, 'MDY')
        if result:
            return result

    # Pattern 4: Statement Date
    m = re.search(r'STATEMENT\s*DATE[:\s]+(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})', text, re.I)
    if m:
        result = _parse_date_match(m, 'MDY')
        if result:
            return result

    # Pattern 5: Multiline Invoice Date
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if re.search(r'INVOICE\s*DATE', line, re.I) and i + 1 < len(lines):
            next_line = lines[i + 1].strip()
            m = re.match(r'^(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})', next_line)
            if m:
                result = _parse_date_match(m, 'MDY')
                if result:
                    return result

    return None


# =============================================================================
# CASELLA
# =============================================================================

def _extract_casella_date(text: str) -> Optional[str]:
    """
    Casella date extraction.

    Format: Various date headers
    """
    # Pattern 1: Invoice Date
    m = re.search(r'INVOICE\s*DATE[:\s]+(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})', text, re.I)
    if m:
        result = _parse_date_match(m, 'MDY')
        if result:
            return result

    # Pattern 2: Date with month name
    m = re.search(r'(?:INVOICE\s*)?DATE[:\s]+([A-Za-z]+)\s+(\d{1,2}),?\s*(\d{4})', text, re.I)
    if m:
        month_name = m.group(1).lower()[:3]
        month = MONTH_MAP.get(month_name)
        if month:
            day, year = int(m.group(2)), int(m.group(3))
            if _validate_date(month, day, year):
                return _format_date(month, day, year)

    # Pattern 3: Multiline
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if re.search(r'\bDATE\b', line, re.I) and 'DUE' not in line.upper():
            if i + 1 < len(lines):
                next_line = lines[i + 1].strip()
                m = re.match(r'^(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})', next_line)
                if m:
                    result = _parse_date_match(m, 'MDY')
                    if result:
                        return result

    return None


# =============================================================================
# FCC ENVIRONMENTAL
# =============================================================================

def _extract_fcc_date(text: str) -> Optional[str]:
    """
    FCC Environmental date extraction.

    Multiple regional formats including reverse columnar.
    Format: Date value ABOVE "Invoice Date:" label
        05/02/25
        Invoice Date:
    """
    text = _normalize_text(text)
    lines = text.split('\n')

    # Pattern 1: Reverse columnar - date value BEFORE "Invoice Date:" label
    for i, line in enumerate(lines):
        if 'INVOICE DATE' in line.upper():
            # Check lines BEFORE the label
            for j in range(max(0, i - 3), i):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    result = _parse_date_match(m, 'MDY')
                    if result:
                        return result

    # Pattern 2: Invoice Date inline
    m = re.search(r'INVOICE\s*DATE[:\s]+(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})', text, re.I)
    if m:
        result = _parse_date_match(m, 'MDY')
        if result:
            return result

    # Pattern 3: Date:
    m = re.search(r'\bDATE[:\s]+(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})', text, re.I)
    if m:
        result = _parse_date_match(m, 'MDY')
        if result:
            return result

    return None


# =============================================================================
# TIGER SANITATION
# =============================================================================

def _extract_tiger_date(text: str) -> Optional[str]:
    """
    Tiger Sanitation date extraction.

    Format: INVOICE NO/DATE headers
    """
    # Pattern 1: Invoice Date
    m = re.search(r'INVOICE\s*DATE[:\s]+(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})', text, re.I)
    if m:
        result = _parse_date_match(m, 'MDY')
        if result:
            return result

    # Pattern 2: DATE header multiline
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if re.search(r'\bDATE\b', line, re.I) and i + 1 < len(lines):
            next_line = lines[i + 1].strip()
            m = re.match(r'^(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})', next_line)
            if m:
                result = _parse_date_match(m, 'MDY')
                if result:
                    return result

    return None


# =============================================================================
# ANYTIME WASTE (NavuSoft)
# =============================================================================

def _extract_anytime_waste_date(text: str) -> Optional[str]:
    """
    Anytime Waste date extraction (NavuSoft format).

    Format: DATE in columnar header, often with month names
    Common patterns:
        DATE
        QUICK PAY CODE
        Apr 30, 2025
    """
    text = _normalize_text(text)
    lines = text.split('\n')

    # Pattern 1: Look for DATE header followed by month name date
    for i, line in enumerate(lines):
        if line.strip().upper() == 'DATE' or re.match(r'^\s*DATE\s*$', line, re.I):
            # Check next lines for month name date (wide columnar — address block between label and value)
            for j in range(i + 1, min(i + 12, len(lines))):
                # Month name format: Apr 30, 2025
                m = re.match(r'^\s*([A-Za-z]+)\s+(\d{1,2}),?\s*(\d{4})\s*$', lines[j].strip())
                if m:
                    month_name = m.group(1).lower()[:3]
                    month = MONTH_MAP.get(month_name)
                    if month:
                        day, year = int(m.group(2)), int(m.group(3))
                        if _validate_date(month, day, year):
                            return _format_date(month, day, year)

                # Numeric format
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    result = _parse_date_match(m, 'MDY')
                    if result:
                        return result

    # Pattern 2: Inline DATE:
    m = re.search(r'\bDATE[:\s]+([A-Za-z]+)\s+(\d{1,2}),?\s*(\d{4})', text, re.I)
    if m:
        month_name = m.group(1).lower()[:3]
        month = MONTH_MAP.get(month_name)
        if month:
            day, year = int(m.group(2)), int(m.group(3))
            if _validate_date(month, day, year):
                return _format_date(month, day, year)

    return None


# =============================================================================
# MERIDIAN WASTE
# =============================================================================

def _extract_meridian_waste_date(text: str) -> Optional[str]:
    """
    Meridian Waste date extraction.

    Format: Columnar header with "Date" label
    OCR shows:
        Invoice
        MERIDIAN
        ...
        Date
        10/15/2025
        Invoice #
        7064469
    """
    text = _normalize_text(text)
    lines = text.split('\n')

    # Pattern 1: Find "Date" header (alone on line), date is next line
    for i, line in enumerate(lines):
        stripped = line.strip().upper()
        if stripped == 'DATE' and i + 1 < len(lines):
            next_line = lines[i + 1].strip()
            m = re.match(r'^(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})$', next_line)
            if m:
                result = _parse_date_match(m, 'MDY')
                if result:
                    return result

    # Pattern 2: Inline Date:
    m = re.search(r'\bDATE[:\s]+(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})', text, re.I)
    if m:
        result = _parse_date_match(m, 'MDY')
        if result:
            return result

    # Pattern 3: Invoice Date
    m = re.search(r'INVOICE\s*DATE[:\s]+(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})', text, re.I)
    if m:
        result = _parse_date_match(m, 'MDY')
        if result:
            return result

    return None


# =============================================================================
# WASTE PRO
# =============================================================================

def _extract_waste_pro_date(text: str) -> Optional[str]:
    """
    Waste Pro date extraction.

    Format: Invoice Date: in header section
    OCR shows:
        Invoice Number:
        ...
        Invoice Date:
        ...
    Date may be inline or on nearby line.
    """
    text = _normalize_text(text)
    lines = text.split('\n')

    # Pattern 1: Invoice Date inline
    m = re.search(r'INVOICE\s*DATE[:\s]+(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})', text, re.I)
    if m:
        result = _parse_date_match(m, 'MDY')
        if result:
            return result

    # Pattern 2: Invoice Date multiline
    for i, line in enumerate(lines):
        if 'INVOICE DATE' in line.upper() or 'INVOICE DATE:' in line.upper():
            # Check next few lines for date
            for j in range(i + 1, min(i + 4, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})', lines[j].strip())
                if m:
                    result = _parse_date_match(m, 'MDY')
                    if result:
                        return result

    # Pattern 3: Bill Date fallback
    m = re.search(r'BILL\s*DATE[:\s]+(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})', text, re.I)
    if m:
        result = _parse_date_match(m, 'MDY')
        if result:
            return result

    return None


# =============================================================================
# ATHENS SERVICES
# =============================================================================

def _extract_athens_date(text: str) -> Optional[str]:
    """
    Athens Services date extraction.

    Format: Columnar headers - INVOICE DATE in header row
    OCR shows:
        INVOICE NUMBER
        INVOICE DATE
        DUE DATE
        BILLING PERIOD
        ...
        (values on later lines)
    """
    text = _normalize_text(text)
    lines = text.split('\n')

    # Pattern 1: Find INVOICE DATE header, look for date in following lines
    for i, line in enumerate(lines):
        if 'INVOICE DATE' in line.upper():
            # Check if inline
            m = re.search(r'INVOICE\s*DATE[:\s]+(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})', line, re.I)
            if m:
                result = _parse_date_match(m, 'MDY')
                if result:
                    return result

            # Check next several lines for date
            for j in range(i + 1, min(i + 8, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    result = _parse_date_match(m, 'MDY')
                    if result:
                        return result

    # Pattern 2: BILLING PERIOD date
    m = re.search(r'BILLING\s*PERIOD[:\s]+(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})', text, re.I)
    if m:
        result = _parse_date_match(m, 'MDY')
        if result:
            return result

    return None


# =============================================================================
# RECOLOGY
# =============================================================================

def _extract_recology_date(text: str) -> Optional[str]:
    """
    Recology date extraction.

    Format: Bill Date: MM/DD/YYYY inline
    OCR shows:
        Account Number:
        Bill Date:
        1080914879
        03/31/2025
    """
    # Pattern 1: Bill Date inline
    m = re.search(r'BILL\s*DATE[:\s]+(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})', text, re.I)
    if m:
        result = _parse_date_match(m, 'MDY')
        if result:
            return result

    # Pattern 2: Bill Date multiline
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if 'BILL DATE' in line.upper():
            # Check next few lines
            for j in range(i + 1, min(i + 4, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})', lines[j].strip())
                if m:
                    result = _parse_date_match(m, 'MDY')
                    if result:
                        return result

    # Pattern 3: Statement Date
    m = re.search(r'STATEMENT\s*DATE[:\s]+(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})', text, re.I)
    if m:
        result = _parse_date_match(m, 'MDY')
        if result:
            return result

    # Pattern 4: Invoice Date
    m = re.search(r'INVOICE\s*DATE[:\s]+(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})', text, re.I)
    if m:
        result = _parse_date_match(m, 'MDY')
        if result:
            return result

    return None


# =============================================================================
# UNIVERSAL WASTE
# =============================================================================

def _extract_universal_waste_date(text: str) -> Optional[str]:
    """
    Universal Waste Systems date extraction.

    Format: Invoice Date: columnar or inline
    OCR shows:
        Invoice Number:
        Invoice Date:
        ...
        0004416419
        12/31/25
    """
    text = _normalize_text(text)
    lines = text.split('\n')

    # Pattern 1: Invoice Date inline
    m = re.search(r'INVOICE\s*DATE[:\s]+(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})', text, re.I)
    if m:
        result = _parse_date_match(m, 'MDY')
        if result:
            return result

    # Pattern 2: Find Invoice Date header, look for date nearby
    for i, line in enumerate(lines):
        if 'INVOICE DATE' in line.upper():
            for j in range(i + 1, min(i + 5, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    result = _parse_date_match(m, 'MDY')
                    if result:
                        return result

    # Pattern 3: Due Date (use as fallback, common on these invoices)
    m = re.search(r'DUE\s*DATE[:\s]+(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})', text, re.I)
    if m:
        result = _parse_date_match(m, 'MDY')
        if result:
            return result

    return None


# =============================================================================
# SUBURBAN DISPOSAL
# =============================================================================

def _extract_suburban_disposal_date(text: str) -> Optional[str]:
    """
    Suburban Disposal date extraction.

    Format: Unique inline format
    OCR shows:
        DATE 03/01/25 ACCOUNT NO.088140-000 AMOUNT DUE 4,218.12
    """
    # Pattern 1: DATE MM/DD/YY ACCOUNT (unique format)
    m = re.search(r'\bDATE\s+(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s+ACCOUNT', text, re.I)
    if m:
        result = _parse_date_match(m, 'MDY')
        if result:
            return result

    # Pattern 2: Standard Date: format
    m = re.search(r'\bDATE[:\s]+(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})', text, re.I)
    if m:
        result = _parse_date_match(m, 'MDY')
        if result:
            return result

    # Pattern 3: Invoice Date
    m = re.search(r'INVOICE\s*DATE[:\s]+(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})', text, re.I)
    if m:
        result = _parse_date_match(m, 'MDY')
        if result:
            return result

    return None


# =============================================================================
# LAKESHORE RECYCLING
# =============================================================================

def _extract_lakeshore_date(text: str) -> Optional[str]:
    """
    Lakeshore Recycling Systems date extraction.

    Format: Various - Invoice Date or Statement Date
    """
    # Pattern 1: Invoice Date
    m = re.search(r'INVOICE\s*DATE[:\s]+(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})', text, re.I)
    if m:
        result = _parse_date_match(m, 'MDY')
        if result:
            return result

    # Pattern 2: Statement Date
    m = re.search(r'STATEMENT\s*DATE[:\s]+(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})', text, re.I)
    if m:
        result = _parse_date_match(m, 'MDY')
        if result:
            return result

    # Pattern 3: Bill Date
    m = re.search(r'BILL\s*DATE[:\s]+(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})', text, re.I)
    if m:
        result = _parse_date_match(m, 'MDY')
        if result:
            return result

    # Pattern 4: Multiline
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if re.search(r'(INVOICE|STATEMENT|BILL)\s*DATE', line, re.I) and i + 1 < len(lines):
            next_line = lines[i + 1].strip()
            m = re.match(r'^(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})', next_line)
            if m:
                result = _parse_date_match(m, 'MDY')
                if result:
                    return result

    return None


# =============================================================================
# COUNTY WASTE
# =============================================================================

def _extract_county_waste_date(text: str) -> Optional[str]:
    """
    County Waste date extraction.
    """
    # Pattern 1: Invoice Date
    m = re.search(r'INVOICE\s*DATE[:\s]+(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})', text, re.I)
    if m:
        result = _parse_date_match(m, 'MDY')
        if result:
            return result

    # Pattern 2: Statement Date
    m = re.search(r'STATEMENT\s*DATE[:\s]+(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})', text, re.I)
    if m:
        result = _parse_date_match(m, 'MDY')
        if result:
            return result

    # Pattern 3: Date:
    m = re.search(r'\bDATE[:\s]+(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})', text, re.I)
    if m:
        result = _parse_date_match(m, 'MDY')
        if result:
            return result

    return None


# =============================================================================
# GRANGER
# =============================================================================

def _extract_granger_date(text: str) -> Optional[str]:
    """
    Granger Waste Services date extraction.
    """
    # Pattern 1: Invoice Date
    m = re.search(r'INVOICE\s*DATE[:\s]+(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})', text, re.I)
    if m:
        result = _parse_date_match(m, 'MDY')
        if result:
            return result

    # Pattern 2: Statement Date
    m = re.search(r'STATEMENT\s*DATE[:\s]+(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})', text, re.I)
    if m:
        result = _parse_date_match(m, 'MDY')
        if result:
            return result

    # Pattern 3: Multiline
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if re.search(r'INVOICE\s*DATE', line, re.I) and i + 1 < len(lines):
            next_line = lines[i + 1].strip()
            m = re.match(r'^(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})', next_line)
            if m:
                result = _parse_date_match(m, 'MDY')
                if result:
                    return result

    return None


# =============================================================================
# ADVANCED DISPOSAL
# =============================================================================

def _extract_advanced_disposal_date(text: str) -> Optional[str]:
    """
    Advanced Disposal date extraction.
    Now part of WM but historical invoices exist.
    """
    # Pattern 1: Invoice Date
    m = re.search(r'INVOICE\s*DATE[:\s]+(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})', text, re.I)
    if m:
        result = _parse_date_match(m, 'MDY')
        if result:
            return result

    # Pattern 2: Statement Date
    m = re.search(r'STATEMENT\s*DATE[:\s]+(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})', text, re.I)
    if m:
        result = _parse_date_match(m, 'MDY')
        if result:
            return result

    # Pattern 3: Bill Date
    m = re.search(r'BILL\s*DATE[:\s]+(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})', text, re.I)
    if m:
        result = _parse_date_match(m, 'MDY')
        if result:
            return result

    return None


# =============================================================================
# GROOT INDUSTRIES
# =============================================================================

def _extract_groot_date(text: str) -> Optional[str]:
    """
    Groot Industries date extraction.
    """
    # Pattern 1: Invoice Date
    m = re.search(r'INVOICE\s*DATE[:\s]+(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})', text, re.I)
    if m:
        result = _parse_date_match(m, 'MDY')
        if result:
            return result

    # Pattern 2: Statement Date
    m = re.search(r'STATEMENT\s*DATE[:\s]+(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})', text, re.I)
    if m:
        result = _parse_date_match(m, 'MDY')
        if result:
            return result

    # Pattern 3: Multiline
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if re.search(r'(INVOICE|STATEMENT)\s*DATE', line, re.I) and i + 1 < len(lines):
            next_line = lines[i + 1].strip()
            m = re.match(r'^(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})', next_line)
            if m:
                result = _parse_date_match(m, 'MDY')
                if result:
                    return result

    return None


# =============================================================================
# EMTERRA ENVIRONMENTAL
# =============================================================================

def _extract_emterra_date(text: str) -> Optional[str]:
    """
    Emterra Environmental date extraction.

    Format: NavuSoft-style columnar with month name dates
    OCR shows:
        INVOICE #
        AMOUNT
        ACCOUNT #
        DATE
        DUE DATE
        ...
        May 1, 2025
    """
    text = _normalize_text(text)
    lines = text.split('\n')

    # Pattern 1: Find DATE header (alone), look for month name date
    for i, line in enumerate(lines):
        stripped = line.strip().upper()
        if stripped == 'DATE':
            # Check next few lines for month name date
            for j in range(i + 1, min(i + 6, len(lines))):
                # Month name format: May 1, 2025
                m = re.match(r'^\s*([A-Za-z]+)\s+(\d{1,2}),?\s*(\d{4})\s*$', lines[j].strip())
                if m:
                    month_name = m.group(1).lower()[:3]
                    month = MONTH_MAP.get(month_name)
                    if month:
                        day, year = int(m.group(2)), int(m.group(3))
                        if _validate_date(month, day, year):
                            return _format_date(month, day, year)

                # Numeric format
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    result = _parse_date_match(m, 'MDY')
                    if result:
                        return result

    # Pattern 2: Invoice Date
    m = re.search(r'INVOICE\s*DATE[:\s]+(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})', text, re.I)
    if m:
        result = _parse_date_match(m, 'MDY')
        if result:
            return result

    return None


# =============================================================================
# ROBINSON WASTE
# =============================================================================

def _extract_robinson_waste_date(text: str) -> Optional[str]:
    """
    Robinson Waste date extraction.

    Format: Columnar with DATE header
    OCR shows:
        INVOICE NO.
        PAGE
        0000363826
        Page 1 of 1
        11/01/2025
        DATE
    """
    text = _normalize_text(text)
    lines = text.split('\n')

    # Pattern 1: Look for DATE header and find date nearby
    for i, line in enumerate(lines):
        stripped = line.strip().upper()
        if stripped == 'DATE':
            # Check surrounding lines for date (before and after)
            for j in range(max(0, i - 3), min(i + 4, len(lines))):
                if j == i:
                    continue
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    result = _parse_date_match(m, 'MDY')
                    if result:
                        return result

    # Pattern 2: Invoice Date inline
    m = re.search(r'INVOICE\s*DATE[:\s]+(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})', text, re.I)
    if m:
        result = _parse_date_match(m, 'MDY')
        if result:
            return result

    # Pattern 3: Find any date pattern near INVOICE header
    m = re.search(r'INVOICE.*?(\d{1,2})[/\-](\d{1,2})[/\-](\d{4})', text, re.I | re.DOTALL)
    if m:
        result = _parse_date_match(m, 'MDY')
        if result:
            return result

    return None


# =============================================================================
# LIGHTNING DISPOSAL
# =============================================================================

def _extract_lightning_disposal_date(text: str) -> Optional[str]:
    """
    Lightning Disposal date extraction.

    Format: Columnar with DATE header
    OCR shows:
        INVOICE NO.
        PAGE
        DATE
        0000773886
        Page 1 of 1
        05/14/2025
    """
    text = _normalize_text(text)
    lines = text.split('\n')

    # Pattern 1: Find DATE header, look for date in following lines
    for i, line in enumerate(lines):
        stripped = line.strip().upper()
        if stripped == 'DATE':
            # Check next several lines
            for j in range(i + 1, min(i + 5, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    result = _parse_date_match(m, 'MDY')
                    if result:
                        return result

    # Pattern 2: Invoice Date inline
    m = re.search(r'INVOICE\s*DATE[:\s]+(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})', text, re.I)
    if m:
        result = _parse_date_match(m, 'MDY')
        if result:
            return result

    # Pattern 3: DATE: inline
    m = re.search(r'\bDATE[:\s]+(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})', text, re.I)
    if m:
        result = _parse_date_match(m, 'MDY')
        if result:
            return result

    return None


# =============================================================================
# ALL WASTE
# =============================================================================

def _extract_all_waste_date(text: str) -> Optional[str]:
    """
    All Waste date extraction.

    Format: Invoice Date with date inline or next line
    OCR shows:
        Invoice #
        Invoice Date
        408203
        01/02/2025
    """
    text = _normalize_text(text)
    lines = text.split('\n')

    # Pattern 1: Invoice Date followed by date on nearby line
    for i, line in enumerate(lines):
        if 'INVOICE DATE' in line.upper():
            # Check next few lines
            for j in range(i + 1, min(i + 4, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    result = _parse_date_match(m, 'MDY')
                    if result:
                        return result

    # Pattern 2: Invoice Date inline
    m = re.search(r'INVOICE\s*DATE[:\s]+(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})', text, re.I)
    if m:
        result = _parse_date_match(m, 'MDY')
        if result:
            return result

    # Pattern 3: Statement Date
    m = re.search(r'STATEMENT\s*DATE[:\s]+(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})', text, re.I)
    if m:
        result = _parse_date_match(m, 'MDY')
        if result:
            return result

    return None


# =============================================================================
# DEBRIS TO GREEN
# =============================================================================

def _extract_debris_to_green_date(text: str) -> Optional[str]:
    """
    Debris to Green date extraction.

    Format: DATE: M/DD/YY inline
    """
    # Pattern 1: DATE: inline
    m = re.search(r'\bDATE[:\s]+(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})', text, re.I)
    if m:
        result = _parse_date_match(m, 'MDY')
        if result:
            return result

    # Pattern 2: Invoice Date
    m = re.search(r'INVOICE\s*DATE[:\s]+(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})', text, re.I)
    if m:
        result = _parse_date_match(m, 'MDY')
        if result:
            return result

    return None


# =============================================================================
# DISPOSAL MANAGEMENT
# =============================================================================

def _extract_disposal_management_date(text: str) -> Optional[str]:
    """
    Disposal Management Services date extraction.

    Format: INV DATE MM/DD/YY inline
    """
    # Pattern 1: INV DATE inline
    m = re.search(r'INV\s*DATE[:\s]+(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})', text, re.I)
    if m:
        result = _parse_date_match(m, 'MDY')
        if result:
            return result

    # Pattern 2: Invoice Date
    m = re.search(r'INVOICE\s*DATE[:\s]+(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})', text, re.I)
    if m:
        result = _parse_date_match(m, 'MDY')
        if result:
            return result

    return None


# =============================================================================
# KNIGHTHORST
# =============================================================================

def _extract_knighthorst_date(text: str) -> Optional[str]:
    """
    KnightHorst Shredding date extraction.

    Format: DATE MM/DD/YYYY inline
    """
    # Pattern 1: DATE inline
    m = re.search(r'\bDATE[:\s]+(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})', text, re.I)
    if m:
        result = _parse_date_match(m, 'MDY')
        if result:
            return result

    # Pattern 2: Invoice Date
    m = re.search(r'INVOICE\s*DATE[:\s]+(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})', text, re.I)
    if m:
        result = _parse_date_match(m, 'MDY')
        if result:
            return result

    return None


# =============================================================================
# WESTERN KANE COUNTY
# =============================================================================

def _extract_western_kane_date(text: str) -> Optional[str]:
    """
    Western Kane County date extraction.

    Format: Invoice Date: M/DD/YYYY inline
    """
    # Pattern 1: Invoice Date inline
    m = re.search(r'INVOICE\s*DATE[:\s]+(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})', text, re.I)
    if m:
        result = _parse_date_match(m, 'MDY')
        if result:
            return result

    # Pattern 2: Statement Date
    m = re.search(r'STATEMENT\s*DATE[:\s]+(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})', text, re.I)
    if m:
        result = _parse_date_match(m, 'MDY')
        if result:
            return result

    return None


# =============================================================================
# PANZARELLA WASTE
# =============================================================================

def _extract_panzarella_date(text: str) -> Optional[str]:
    """
    Panzarella Waste date extraction.

    Format: Columnar Date header with date 1-3 lines later
    OCR shows: Date / Invoice # / 04/28/2025 / 384585
    """
    text = _normalize_text(text)
    lines = text.split('\n')

    # Pattern 1: Find Date header alone, date within next 3 lines
    for i, line in enumerate(lines):
        stripped = line.strip().upper()
        if stripped == 'DATE':
            for j in range(i + 1, min(i + 4, len(lines))):
                next_line = lines[j].strip()
                m = re.match(r'^(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})$', next_line)
                if m:
                    result = _parse_date_match(m, 'MDY')
                    if result:
                        return result

    # Pattern 2: Invoice Date inline
    m = re.search(r'INVOICE\s*DATE[:\s]+(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})', text, re.I)
    if m:
        result = _parse_date_match(m, 'MDY')
        if result:
            return result

    return None


# =============================================================================
# SUNRISE SANITATION
# =============================================================================

def _extract_sunrise_sanitation_date(text: str) -> Optional[str]:
    """
    Sunrise Sanitation Service date extraction.

    Format: Columnar Date header with date 1-3 lines later
    OCR shows: Date / Invoice # / 4/30/2025 / 96872
    """
    text = _normalize_text(text)
    lines = text.split('\n')

    # Pattern 1: Find Date header alone, date within next 3 lines
    for i, line in enumerate(lines):
        stripped = line.strip().upper()
        if stripped == 'DATE':
            for j in range(i + 1, min(i + 4, len(lines))):
                next_line = lines[j].strip()
                m = re.match(r'^(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})$', next_line)
                if m:
                    result = _parse_date_match(m, 'MDY')
                    if result:
                        return result

    # Pattern 2: Invoice Date inline
    m = re.search(r'INVOICE\s*DATE[:\s]+(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})', text, re.I)
    if m:
        result = _parse_date_match(m, 'MDY')
        if result:
            return result

    return None


# =============================================================================
# USA WASTE
# =============================================================================

def _extract_usa_waste_date(text: str) -> Optional[str]:
    """
    USA Waste & Recycling date extraction.

    Format: INVOICE DATE: MM/DD/YYYY inline
    """
    # Pattern 1: INVOICE DATE inline
    m = re.search(r'INVOICE\s*DATE[:\s]+(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})', text, re.I)
    if m:
        result = _parse_date_match(m, 'MDY')
        if result:
            return result

    # Pattern 2: Statement Date
    m = re.search(r'STATEMENT\s*DATE[:\s]+(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})', text, re.I)
    if m:
        result = _parse_date_match(m, 'MDY')
        if result:
            return result

    return None


# =============================================================================
# BEST CLEANER
# =============================================================================

def _extract_best_cleaner_date(text: str) -> Optional[str]:
    """
    Best Cleaner Disposal date extraction.

    Format: Weekday Month DD, YYYY (e.g., "Tue Sep 16, 2025")
    """
    # Pattern 1: Weekday Month DD, YYYY
    m = re.search(r'(?:Mon|Tue|Wed|Thu|Fri|Sat|Sun)\s+([A-Za-z]+)\s+(\d{1,2}),?\s*(\d{4})', text, re.I)
    if m:
        month_name = m.group(1).lower()[:3]
        month = MONTH_MAP.get(month_name)
        if month:
            day, year = int(m.group(2)), int(m.group(3))
            if _validate_date(month, day, year):
                return _format_date(month, day, year)

    # Pattern 2: Month DD, YYYY without weekday
    m = re.search(r'([A-Za-z]+)\s+(\d{1,2}),?\s*(\d{4})', text, re.I)
    if m:
        month_name = m.group(1).lower()[:3]
        month = MONTH_MAP.get(month_name)
        if month:
            day, year = int(m.group(2)), int(m.group(3))
            if _validate_date(month, day, year):
                return _format_date(month, day, year)

    # Pattern 3: Invoice Date
    m = re.search(r'INVOICE\s*DATE[:\s]+(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})', text, re.I)
    if m:
        result = _parse_date_match(m, 'MDY')
        if result:
            return result

    return None


# =============================================================================
# BULLDOG DISPOSAL
# =============================================================================

def _extract_bulldog_disposal_date(text: str) -> Optional[str]:
    """
    Bulldog Disposal date extraction.

    Format: INV DATE MM/DD/YY inline
    """
    # Pattern 1: INV DATE inline
    m = re.search(r'INV\s*DATE[:\s]+(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})', text, re.I)
    if m:
        result = _parse_date_match(m, 'MDY')
        if result:
            return result

    # Pattern 2: Invoice Date
    m = re.search(r'INVOICE\s*DATE[:\s]+(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})', text, re.I)
    if m:
        result = _parse_date_match(m, 'MDY')
        if result:
            return result

    return None


# =============================================================================
# COCKEY'S ENTERPRISES
# =============================================================================

def _extract_cockeys_date(text: str) -> Optional[str]:
    """
    Cockey's Enterprises date extraction.

    Format: Columnar DATE header (NavuSoft style)
    """
    text = _normalize_text(text)
    lines = text.split('\n')

    # Pattern 1: Find DATE header alone, date within next 4 lines
    for i, line in enumerate(lines):
        stripped = line.strip().upper()
        if stripped == 'DATE':
            for j in range(i + 1, min(i + 5, len(lines))):
                # Numeric date
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    result = _parse_date_match(m, 'MDY')
                    if result:
                        return result
                # Month name date
                m = re.match(r'^\s*([A-Za-z]+)\s+(\d{1,2}),?\s*(\d{4})\s*$', lines[j].strip())
                if m:
                    month_name = m.group(1).lower()[:3]
                    month = MONTH_MAP.get(month_name)
                    if month:
                        day, year = int(m.group(2)), int(m.group(3))
                        if _validate_date(month, day, year):
                            return _format_date(month, day, year)

    # Pattern 2: Invoice Date inline
    m = re.search(r'INVOICE\s*DATE[:\s]+(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})', text, re.I)
    if m:
        result = _parse_date_match(m, 'MDY')
        if result:
            return result

    return None


# =============================================================================
# SBC WASTE
# =============================================================================

def _extract_sbc_waste_date(text: str) -> Optional[str]:
    """
    SBC Waste Solutions date extraction.

    Format: Invoice Date in columnar header
    """
    text = _normalize_text(text)
    lines = text.split('\n')

    # Pattern 1: Invoice Date header, date on later line
    for i, line in enumerate(lines):
        if 'INVOICE DATE' in line.upper():
            # Check if inline
            m = re.search(r'INVOICE\s*DATE[:\s]+(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})', line, re.I)
            if m:
                result = _parse_date_match(m, 'MDY')
                if result:
                    return result
            # Check next lines
            for j in range(i + 1, min(i + 6, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    result = _parse_date_match(m, 'MDY')
                    if result:
                        return result

    return None


# =============================================================================
# WALTERS RECYCLING
# =============================================================================

def _extract_walters_date(text: str) -> Optional[str]:
    """
    Walters Recycling date extraction.

    Format: INVOICE DATE multiline with date below
    """
    text = _normalize_text(text)
    lines = text.split('\n')

    # Pattern 1: INVOICE DATE header, date on next line
    for i, line in enumerate(lines):
        if 'INVOICE DATE' in line.upper():
            for j in range(i + 1, min(i + 4, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    result = _parse_date_match(m, 'MDY')
                    if result:
                        return result

    # Pattern 2: Inline
    m = re.search(r'INVOICE\s*DATE[:\s]+(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})', text, re.I)
    if m:
        result = _parse_date_match(m, 'MDY')
        if result:
            return result

    return None


# =============================================================================
# TRANSTRASH
# =============================================================================

def _extract_transtrash_date(text: str) -> Optional[str]:
    """
    TransTrash date extraction.

    Format: Columnar DATE header with month name format
    """
    text = _normalize_text(text)
    lines = text.split('\n')

    # Pattern 1: Find DATE header, look for month name date
    for i, line in enumerate(lines):
        stripped = line.strip().upper()
        if stripped == 'DATE':
            for j in range(i + 1, min(i + 5, len(lines))):
                # Month name: May 31, 2025
                m = re.match(r'^\s*([A-Za-z]+)\s+(\d{1,2}),?\s*(\d{4})\s*$', lines[j].strip())
                if m:
                    month_name = m.group(1).lower()[:3]
                    month = MONTH_MAP.get(month_name)
                    if month:
                        day, year = int(m.group(2)), int(m.group(3))
                        if _validate_date(month, day, year):
                            return _format_date(month, day, year)
                # Numeric
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    result = _parse_date_match(m, 'MDY')
                    if result:
                        return result

    # Pattern 2: DUE DATE with month name (fallback - use invoice date minus ~15 days concept)
    m = re.search(r'DUE\s*DATE[:\s]+([A-Za-z]+)\s+(\d{1,2}),?\s*(\d{4})', text, re.I)
    if m:
        month_name = m.group(1).lower()[:3]
        month = MONTH_MAP.get(month_name)
        if month:
            day, year = int(m.group(2)), int(m.group(3))
            if _validate_date(month, day, year):
                return _format_date(month, day, year)

    return None


# =============================================================================
# CONIGLIARO
# =============================================================================

def _extract_conigliaro_date(text: str) -> Optional[str]:
    """
    Conigliaro Industries date extraction.

    Format: Columnar Date header with date on next line
    """
    text = _normalize_text(text)
    lines = text.split('\n')

    # Pattern 1: Find Date header alone, date on next line
    for i, line in enumerate(lines):
        stripped = line.strip().upper()
        if stripped == 'DATE':
            for j in range(i + 1, min(i + 4, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    result = _parse_date_match(m, 'MDY')
                    if result:
                        return result

    # Pattern 2: Invoice Date inline
    m = re.search(r'INVOICE\s*DATE[:\s]+(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})', text, re.I)
    if m:
        result = _parse_date_match(m, 'MDY')
        if result:
            return result

    return None


# =============================================================================
# WOMPOST (City of Clearwater)
# =============================================================================

def _extract_wompost_date(text: str) -> Optional[str]:
    """
    Wompost / City of Clearwater date extraction.

    Format: STATEMENT DATE: M/DD/YYYY inline
    """
    # Pattern 1: STATEMENT DATE inline
    m = re.search(r'STATEMENT\s*DATE[:\s]+(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})', text, re.I)
    if m:
        result = _parse_date_match(m, 'MDY')
        if result:
            return result

    # Pattern 2: Bill Date
    m = re.search(r'BILL\s*DATE[:\s]+(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})', text, re.I)
    if m:
        result = _parse_date_match(m, 'MDY')
        if result:
            return result

    # Pattern 3: Multiline Statement Date
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if 'STATEMENT DATE' in line.upper() and i + 1 < len(lines):
            next_line = lines[i + 1].strip()
            m = re.match(r'^(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})', next_line)
            if m:
                result = _parse_date_match(m, 'MDY')
                if result:
                    return result

    return None


# =============================================================================
# BOREN BROTHERS
# =============================================================================

def _extract_boren_brothers_date(text: str) -> Optional[str]:
    """
    Boren Brothers date extraction.

    Format: INVOICE DATE M/D/YYYY multiline
    """
    text = _normalize_text(text)
    lines = text.split('\n')

    # Pattern 1: INVOICE DATE header, date on next line
    for i, line in enumerate(lines):
        if 'INVOICE DATE' in line.upper():
            for j in range(i + 1, min(i + 3, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    result = _parse_date_match(m, 'MDY')
                    if result:
                        return result

    # Pattern 2: Inline
    m = re.search(r'INVOICE\s*DATE[:\s]+(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})', text, re.I)
    if m:
        result = _parse_date_match(m, 'MDY')
        if result:
            return result

    return None


# =============================================================================
# SOUTH SHORE DISPOSAL
# =============================================================================

def _extract_south_shore_date(text: str) -> Optional[str]:
    """
    South Shore Disposal date extraction.

    Format: INV DATE MM/DD/YY inline
    """
    # Pattern 1: INV DATE inline
    m = re.search(r'INV\s*DATE[:\s]+(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})', text, re.I)
    if m:
        result = _parse_date_match(m, 'MDY')
        if result:
            return result

    # Pattern 2: Invoice Date
    m = re.search(r'INVOICE\s*DATE[:\s]+(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})', text, re.I)
    if m:
        result = _parse_date_match(m, 'MDY')
        if result:
            return result

    return None


# =============================================================================
# BEST WAY DISPOSAL
# =============================================================================

def _extract_best_way_date(text: str) -> Optional[str]:
    """
    Best Way Disposal date extraction.

    Format: Invoice Date or Statement Date
    """
    # Pattern 1: Invoice Date inline
    m = re.search(r'INVOICE\s*DATE[:\s]+(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})', text, re.I)
    if m:
        result = _parse_date_match(m, 'MDY')
        if result:
            return result

    # Pattern 2: Statement Date
    m = re.search(r'STATEMENT\s*DATE[:\s]+(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})', text, re.I)
    if m:
        result = _parse_date_match(m, 'MDY')
        if result:
            return result

    # Pattern 3: Invoice Number line often has date nearby
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if 'INVOICE NUMBER' in line.upper() or 'INVOICE DATE' in line.upper():
            for j in range(i + 1, min(i + 4, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    result = _parse_date_match(m, 'MDY')
                    if result:
                        return result

    return None


# =============================================================================
# FLOOD BROTHERS
# =============================================================================

def _extract_flood_brothers_date(text: str) -> Optional[str]:
    """Flood Brothers - BILLING DATE: columnar or inline
    Format:
        BILLING DATE:
        07/07/2025
    """
    text = _normalize_text(text)
    lines = text.split('\n')

    # Pattern 1: Columnar - BILLING DATE: on one line, date on next
    for i, line in enumerate(lines):
        if 'BILLING DATE' in line.upper():
            # Check next lines for date value
            for j in range(i + 1, min(i + 4, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')

    # Pattern 2: BILLING DATE inline
    m = re.search(r'BILLING\s*DATE[:\s]+(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})', text, re.I)
    if m:
        return _parse_date_match(m, 'MDY')

    # Pattern 3: INVOICE DATE inline
    m = re.search(r'INVOICE\s*DATE[:\s]+(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})', text, re.I)
    if m:
        return _parse_date_match(m, 'MDY')

    return None


# =============================================================================
# EMPIRE WASTE
# =============================================================================

def _extract_empire_waste_date(text: str) -> Optional[str]:
    """Empire Waste - Columnar DATE header (NavuSoft)"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if line.strip().upper() == 'DATE':
            for j in range(i + 1, min(i + 5, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
                # Month name
                m = re.match(r'^\s*([A-Za-z]+)\s+(\d{1,2}),?\s*(\d{4})\s*$', lines[j].strip())
                if m:
                    month = MONTH_MAP.get(m.group(1).lower()[:3])
                    if month:
                        day, year = int(m.group(2)), int(m.group(3))
                        if _validate_date(month, day, year):
                            return _format_date(month, day, year)
    return None


# =============================================================================
# MIDWEST PAPER
# =============================================================================

def _extract_midwest_paper_date(text: str) -> Optional[str]:
    """Midwest Paper - Columnar DATE header"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if line.strip().upper() == 'DATE':
            for j in range(i + 1, min(i + 5, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    m = re.search(r'\bDATE[:\s]+(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})', text, re.I)
    if m:
        return _parse_date_match(m, 'MDY')
    return None


# =============================================================================
# COASTAL WASTE
# =============================================================================

def _extract_coastal_waste_date(text: str) -> Optional[str]:
    """Coastal Waste - Columnar Date header"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if line.strip().upper() == 'DATE':
            for j in range(i + 1, min(i + 5, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    m = re.search(r'INVOICE\s*DATE[:\s]+(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})', text, re.I)
    if m:
        return _parse_date_match(m, 'MDY')
    return None


# =============================================================================
# STANDARD WASTE
# =============================================================================

def _extract_standard_waste_date(text: str) -> Optional[str]:
    """Standard Waste - Date MM/DD/YY inline"""
    text = _normalize_text(text)
    m = re.search(r'\bDate\s+(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})', text, re.I)
    if m:
        return _parse_date_match(m, 'MDY')
    m = re.search(r'INVOICE\s*DATE[:\s]+(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})', text, re.I)
    if m:
        return _parse_date_match(m, 'MDY')
    return None


# =============================================================================
# FRONTIER WASTE
# =============================================================================

def _extract_frontier_waste_date(text: str) -> Optional[str]:
    """Frontier Waste - Columnar DATE with month name"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if line.strip().upper() == 'DATE':
            for j in range(i + 1, min(i + 5, len(lines))):
                # Month name: Mar 15, 2025
                m = re.match(r'^\s*([A-Za-z]+)\s+(\d{1,2}),?\s*(\d{4})\s*$', lines[j].strip())
                if m:
                    month = MONTH_MAP.get(m.group(1).lower()[:3])
                    if month:
                        day, year = int(m.group(2)), int(m.group(3))
                        if _validate_date(month, day, year):
                            return _format_date(month, day, year)
                # Numeric
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


# =============================================================================
# WASTE ELIMINATOR
# =============================================================================

def _extract_waste_eliminator_date(text: str) -> Optional[str]:
    """Waste Eliminator - Columnar Date header"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if line.strip().upper() == 'DATE':
            for j in range(i + 1, min(i + 4, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    m = re.search(r'INVOICE\s*DATE[:\s]+(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})', text, re.I)
    if m:
        return _parse_date_match(m, 'MDY')
    return None


# =============================================================================
# HARTER'S
# =============================================================================

def _extract_harters_date(text: str) -> Optional[str]:
    """Harter's - Invoice Date: MM/DD/YYYY inline"""
    m = re.search(r'INVOICE\s*DATE[:\s]+(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})', text, re.I)
    if m:
        return _parse_date_match(m, 'MDY')
    m = re.search(r'STATEMENT\s*DATE[:\s]+(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})', text, re.I)
    if m:
        return _parse_date_match(m, 'MDY')
    return None


# =============================================================================
# SMITH CREEK
# =============================================================================

def _extract_smith_creek_date(text: str) -> Optional[str]:
    """Smith Creek - Columnar DATE header"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if line.strip().upper() == 'DATE':
            for j in range(i + 1, min(i + 4, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    m = re.search(r'\bDATE[:\s]+(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})', text, re.I)
    if m:
        return _parse_date_match(m, 'MDY')
    return None


# =============================================================================
# ASPEN WASTE
# =============================================================================

def _extract_aspen_waste_date(text: str) -> Optional[str]:
    """Aspen Waste - Statement Date MM/DD/YYYY inline"""
    m = re.search(r'STATEMENT\s*DATE[:\s]+(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})', text, re.I)
    if m:
        return _parse_date_match(m, 'MDY')
    m = re.search(r'INVOICE\s*DATE[:\s]+(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})', text, re.I)
    if m:
        return _parse_date_match(m, 'MDY')
    return None


# =============================================================================
# ACTIVE WASTE
# =============================================================================

def _extract_active_waste_date(text: str) -> Optional[str]:
    """Active Waste - Columnar DATE header (NavuSoft)"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if line.strip().upper() == 'DATE':
            for j in range(i + 1, min(i + 5, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
                # Month name
                m = re.match(r'^\s*([A-Za-z]+)\s+(\d{1,2}),?\s*(\d{4})\s*$', lines[j].strip())
                if m:
                    month = MONTH_MAP.get(m.group(1).lower()[:3])
                    if month:
                        day, year = int(m.group(2)), int(m.group(3))
                        if _validate_date(month, day, year):
                            return _format_date(month, day, year)
    return None


# =============================================================================
# TRANCHE 7 (February 2026)
# =============================================================================

def _extract_hamilton_alliance_date(text: str) -> Optional[str]:
    """Hamilton Alliance - NavuSoft columnar: Date header with date on separate line"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if line.strip().upper() == 'DATE':
            for j in range(i + 1, min(i + 5, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


def _extract_priority_waste_date(text: str) -> Optional[str]:
    """Priority Waste - Date value on line BEFORE 'Date:' label (reverse columnar)"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if line.strip().upper().startswith('DATE:') or line.strip().upper() == 'DATE':
            # Check lines BEFORE the Date: label (reverse columnar format)
            for j in range(max(0, i - 3), i):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
            # Also check after (in case of normal layout)
            for j in range(i + 1, min(i + 3, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    # Fallback: inline Date: MM/DD/YYYY
    m = re.search(r'Date:\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})', text, re.IGNORECASE)
    if m:
        return _parse_date_match(m, 'MDY')
    return None


def _extract_smarttrash_date(text: str) -> Optional[str]:
    """SmartTrash - Date on line after invoice number
    Format:
        #INV023051
        05/01/2025
    """
    text = _normalize_text(text)
    lines = text.split('\n')

    # Pattern 1: Date on line after #INV invoice number
    for i, line in enumerate(lines):
        if line.strip().startswith('#INV'):
            for j in range(i + 1, min(i + 3, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')

    # Pattern 2: Date: inline
    m = re.search(r'(?:^|\n)\s*Date:\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})', text, re.IGNORECASE)
    if m:
        return _parse_date_match(m, 'MDY')

    return None


def _extract_lrs_date(text: str) -> Optional[str]:
    """LRS - Columnar Invoice Date with Mon-DD-YY format (values BEFORE headers)"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if 'INVOICE DATE' in line.upper():
            # Check lines BEFORE the Invoice Date header (reverse columnar format)
            for j in range(max(0, i - 5), i):
                # Mon-DD-YY format
                m = re.search(r'([A-Za-z]{3})-(\d{1,2})-(\d{2,4})', lines[j])
                if m:
                    month = MONTH_MAP.get(m.group(1).lower()[:3])
                    if month:
                        day, year = int(m.group(2)), int(m.group(3))
                        if year < 100:
                            year = 2000 + year if year < 50 else 1900 + year
                        if _validate_date(month, day, year):
                            return _format_date(month, day, year)
            # Check same line
            m = re.search(r'([A-Za-z]{3})-(\d{1,2})-(\d{2,4})', line)
            if m:
                month = MONTH_MAP.get(m.group(1).lower()[:3])
                if month:
                    day, year = int(m.group(2)), int(m.group(3))
                    if year < 100:
                        year = 2000 + year if year < 50 else 1900 + year
                    if _validate_date(month, day, year):
                        return _format_date(month, day, year)
            # Check next few lines (normal columnar)
            for j in range(i + 1, min(i + 5, len(lines))):
                m = re.search(r'([A-Za-z]{3})-(\d{1,2})-(\d{2,4})', lines[j])
                if m:
                    month = MONTH_MAP.get(m.group(1).lower()[:3])
                    if month:
                        day, year = int(m.group(2)), int(m.group(3))
                        if year < 100:
                            year = 2000 + year if year < 50 else 1900 + year
                        if _validate_date(month, day, year):
                            return _format_date(month, day, year)
                # Also try MM/DD/YYYY
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


def _extract_eagle_disposal_date(text: str) -> Optional[str]:
    """Eagle Disposal (TrashBilling) - Weekday Month DD, YYYY format"""
    # Pattern: Wed Oct 1, 2025
    m = re.search(r'(?:Mon|Tue|Wed|Thu|Fri|Sat|Sun)\s+([A-Za-z]{3})\s+(\d{1,2}),?\s*(\d{4})', text)
    if m:
        month = MONTH_MAP.get(m.group(1).lower()[:3])
        if month:
            day, year = int(m.group(2)), int(m.group(3))
            if _validate_date(month, day, year):
                return _format_date(month, day, year)
    return None


def _extract_fusion_waste_date(text: str) -> Optional[str]:
    """Fusion Waste - Columnar INVOICE DATE header"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if 'INVOICE DATE' in line.upper():
            for j in range(i + 1, min(i + 5, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


def _extract_alaska_waste_date(text: str) -> Optional[str]:
    """Alaska Waste - NavuSoft STATEMENT DATE columnar format"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if 'STATEMENT DATE' in line.upper():
            for j in range(i + 1, min(i + 6, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


def _extract_papillion_sanitation_date(text: str) -> Optional[str]:
    """Papillion Sanitation - NavuSoft STATEMENT DATE columnar format"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if 'STATEMENT DATE' in line.upper():
            for j in range(i + 1, min(i + 6, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


def _extract_navajo_sanitation_date(text: str) -> Optional[str]:
    """Navajo Sanitation (TrashBilling) - look for date in payment receipt"""
    # Pattern: received on 7/29/2025 or Date: MM/DD/YY
    m = re.search(r'received on (\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})', text, re.IGNORECASE)
    if m:
        return _parse_date_match(m, 'MDY')
    # Try Weekday Month DD, YYYY format
    m = re.search(r'(?:Mon|Tue|Wed|Thu|Fri|Sat|Sun)\s+([A-Za-z]{3})\s+(\d{1,2}),?\s*(\d{4})', text)
    if m:
        month = MONTH_MAP.get(m.group(1).lower()[:3])
        if month:
            day, year = int(m.group(2)), int(m.group(3))
            if _validate_date(month, day, year):
                return _format_date(month, day, year)
    return None


def _extract_american_disposal_date(text: str) -> Optional[str]:
    """American Disposal - multiple formats
    Format 1 (Waste Connections):
        STATEMENT DATE
        DUE DATE
        BILLING PERIOD
        6319-621138 (account)
        13981357W319 (invoice)
        05/01/25     <- STATEMENT DATE value
    Format 2 (Systems Inc):
        Date
        Invoice #
        ...
        10/31/2025  <- Date value
        17358       <- Invoice # value
    """
    text = _normalize_text(text)
    lines = text.split('\n')

    # Pattern 1: Wide columnar - STATEMENT DATE with value 4-8 lines below
    for i, line in enumerate(lines):
        if 'STATEMENT DATE' in line.upper():
            for j in range(i + 3, min(i + 10, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')

    # Pattern 2: Date header followed by date value (Systems Inc format)
    for i, line in enumerate(lines):
        stripped = line.strip().lower()
        if stripped == 'date':
            # Look for date value in following lines
            for j in range(i + 1, min(i + 8, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')

    # Pattern 3: Date: inline
    m = re.search(r'(?:^|\n)\s*Date:\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})', text, re.IGNORECASE)
    if m:
        return _parse_date_match(m, 'MDY')

    return None


# =============================================================================
# TRANCHE 8 (February 2026)
# =============================================================================

def _extract_lawrence_waste_date(text: str) -> Optional[str]:
    """Lawrence Waste - Columnar DATE header with date on next line"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if line.strip().upper() == 'DATE':
            for j in range(i + 1, min(i + 5, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


def _extract_murreys_disposal_date(text: str) -> Optional[str]:
    """Murreys Disposal - NavuSoft STATEMENT DATE columnar format"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if 'STATEMENT DATE' in line.upper():
            for j in range(i + 1, min(i + 6, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


def _extract_ware_disposal_date(text: str) -> Optional[str]:
    """Ware Disposal - Columnar Date header with date on separate line"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if line.strip().upper() == 'DATE':
            # Check next few lines for date
            for j in range(i + 1, min(i + 5, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
        # Also check for "Invoice" followed by "Date" on separate lines
        if line.strip().upper() == 'INVOICE':
            for j in range(i + 1, min(i + 3, len(lines))):
                if lines[j].strip().upper() == 'DATE':
                    for k in range(j + 1, min(j + 5, len(lines))):
                        m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[k].strip())
                        if m:
                            return _parse_date_match(m, 'MDY')
    return None


def _extract_capital_waste_date(text: str) -> Optional[str]:
    """Capital Waste - NavuSoft-style columnar with Month DD, YYYY format (values far below headers)"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if line.strip().upper() == 'DATE':
            # Search up to 8 lines for date value (NavuSoft puts values far below headers)
            for j in range(i + 1, min(i + 9, len(lines))):
                # Month DD, YYYY format
                m = re.match(r'^\s*([A-Za-z]+)\s+(\d{1,2}),?\s*(\d{4})\s*$', lines[j].strip())
                if m:
                    month = MONTH_MAP.get(m.group(1).lower()[:3])
                    if month:
                        day, year = int(m.group(2)), int(m.group(3))
                        if _validate_date(month, day, year):
                            return _format_date(month, day, year)
                # Also try MM/DD/YYYY
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


def _extract_friedman_recycling_date(text: str) -> Optional[str]:
    """Friedman Recycling - Columnar Invoice Date (values far below headers)"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if 'INVOICE DATE' in line.upper():
            # Search up to 8 lines for date value (columnar format with many fields)
            for j in range(i + 1, min(i + 9, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


def _extract_win_waste_date(text: str) -> Optional[str]:
    """Win Waste - Inline DATE Mon-DD-YY format"""
    # Pattern: DATE Jun-01-25
    m = re.search(r'(?:^|\n)\s*DATE\s+([A-Za-z]{3})-(\d{1,2})-(\d{2,4})', text, re.IGNORECASE)
    if m:
        month = MONTH_MAP.get(m.group(1).lower()[:3])
        if month:
            day, year = int(m.group(2)), int(m.group(3))
            if year < 100:
                year = 2000 + year if year < 50 else 1900 + year
            if _validate_date(month, day, year):
                return _format_date(month, day, year)
    # Also try columnar format
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if line.strip().upper() == 'DATE':
            for j in range(i + 1, min(i + 5, len(lines))):
                m = re.match(r'^\s*([A-Za-z]{3})-(\d{1,2})-(\d{2,4})\s*$', lines[j].strip())
                if m:
                    month = MONTH_MAP.get(m.group(1).lower()[:3])
                    if month:
                        day, year = int(m.group(2)), int(m.group(3))
                        if year < 100:
                            year = 2000 + year if year < 50 else 1900 + year
                        if _validate_date(month, day, year):
                            return _format_date(month, day, year)
    return None


def _extract_novak_sanitary_date(text: str) -> Optional[str]:
    """Novak Sanitary - NavuSoft STATEMENT DATE columnar format"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if 'STATEMENT DATE' in line.upper():
            for j in range(i + 1, min(i + 6, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


def _extract_crr_date(text: str) -> Optional[str]:
    """CR&R - Reverse columnar Invoice Date (date appears BEFORE label)"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if 'INVOICE DATE' in line.upper():
            # Check lines BEFORE the Invoice Date label (reverse columnar format)
            for j in range(max(0, i - 5), i):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
            # Also check after (normal columnar)
            for j in range(i + 1, min(i + 5, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


def _extract_burrtec_date(text: str) -> Optional[str]:
    """Burrtec - Columnar Statement Date"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if 'STATEMENT DATE' in line.upper():
            for j in range(i + 1, min(i + 5, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


def _extract_american_recycling_date(text: str) -> Optional[str]:
    """American Recycling - Scale ticket Date In format"""
    # Pattern: Date In 11/21/25
    m = re.search(r'Date\s+In\s+(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})', text, re.IGNORECASE)
    if m:
        return _parse_date_match(m, 'MDY')
    return None


def _extract_homewood_disposal_date(text: str) -> Optional[str]:
    """Homewood Disposal - Columnar Billing Date"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if 'BILLING DATE' in line.upper():
            for j in range(i + 1, min(i + 5, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


def _extract_ecosouth_date(text: str) -> Optional[str]:
    """EcoSouth - Columnar Date header (OCR splits Invoice/Date across lines, values far below)"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if line.strip().upper() == 'DATE':
            # Search up to 10 lines for date value (OCR can split headers/values widely)
            for j in range(i + 1, min(i + 11, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


# =============================================================================
# TRANCHE 9 (February 2026)
# =============================================================================

def _extract_stryker_environmental_date(text: str) -> Optional[str]:
    """Stryker Environmental - Inline Invoice date: MM/DD/YYYY"""
    m = re.search(r'Invoice\s+date:\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})', text, re.IGNORECASE)
    if m:
        return _parse_date_match(m, 'MDY')
    return None


def _extract_compactor_rentals_date(text: str) -> Optional[str]:
    """Compactor Rentals of America - Reverse columnar Invoice date (date BEFORE label)"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if 'INVOICE DATE' in line.upper():
            # Check lines BEFORE the Invoice date label (reverse columnar format)
            for j in range(max(0, i - 6), i):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
            # Also check after (normal columnar)
            for j in range(i + 1, min(i + 5, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


def _extract_national_equipment_date(text: str) -> Optional[str]:
    """National Equipment Solutions - Columnar Date: with date on separate line"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if line.strip().upper().startswith('DATE:'):
            # Check next few lines for date
            for j in range(i + 1, min(i + 5, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    # Fallback: inline Date: MM/DD/YY
    m = re.search(r'Date:\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})', text, re.IGNORECASE)
    if m:
        return _parse_date_match(m, 'MDY')
    return None


def _extract_redbox_date(text: str) -> Optional[str]:
    """Redbox+ - Inline Invoice Date: MM/DD/YYYY"""
    m = re.search(r'Invoice\s+Date:\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})', text, re.IGNORECASE)
    if m:
        return _parse_date_match(m, 'MDY')
    return None


def _extract_specific_waste_date(text: str) -> Optional[str]:
    """Specific Waste - Columnar Date: with MM-DD-YYYY format (dashes)"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if line.strip().upper().startswith('DATE:') or line.strip().upper() == 'DATE':
            # Check next few lines for date with dashes
            for j in range(i + 1, min(i + 5, len(lines))):
                # MM-DD-YYYY format (with dashes)
                m = re.match(r'^\s*(\d{1,2})-(\d{1,2})-(\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
                # Also try slash format
                m = re.match(r'^\s*(\d{1,2})[/](\d{1,2})[/](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    # Fallback: inline Date: MM-DD-YYYY
    m = re.search(r'Date:\s*(\d{1,2})-(\d{1,2})-(\d{2,4})', text, re.IGNORECASE)
    if m:
        return _parse_date_match(m, 'MDY')
    return None


def _extract_rocky_ridge_date(text: str) -> Optional[str]:
    """Rocky Ridge - Inline DATE MM/DD/YYYY"""
    m = re.search(r'(?:^|\n)\s*DATE\s+(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})', text, re.IGNORECASE)
    if m:
        return _parse_date_match(m, 'MDY')
    return None


def _extract_tower_compactor_date(text: str) -> Optional[str]:
    """Tower Compactor - Columnar Date header"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if line.strip().upper() == 'DATE':
            for j in range(i + 1, min(i + 5, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


def _extract_liberty_waste_date(text: str) -> Optional[str]:
    """Liberty Waste - Columnar Date/Invoice # header"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if line.strip().upper() == 'DATE':
            for j in range(i + 1, min(i + 5, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


def _extract_kimble_date(text: str) -> Optional[str]:
    """Kimble - Columnar INVOICE DATE header"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if 'INVOICE DATE' in line.upper():
            for j in range(i + 1, min(i + 5, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


def _extract_delta_waste_date(text: str) -> Optional[str]:
    """Delta Waste - NavuSoft DATE columnar with Month DD, YYYY format"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if line.strip().upper() == 'DATE':
            for j in range(i + 1, min(i + 8, len(lines))):
                # Month DD, YYYY format
                m = re.match(r'^\s*([A-Za-z]+)\s+(\d{1,2}),?\s*(\d{4})\s*$', lines[j].strip())
                if m:
                    month = MONTH_MAP.get(m.group(1).lower()[:3])
                    if month:
                        day, year = int(m.group(2)), int(m.group(3))
                        if _validate_date(month, day, year):
                            return _format_date(month, day, year)
                # Also try MM/DD/YYYY
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


def _extract_howard_disposal_date(text: str) -> Optional[str]:
    """Howard Disposal - Columnar Date/Invoice # header"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if line.strip().upper() == 'DATE':
            for j in range(i + 1, min(i + 5, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


def _extract_idaho_falls_date(text: str) -> Optional[str]:
    """Idaho Falls Utilities - Columnar Bill Date"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if 'BILL DATE' in line.upper():
            for j in range(i + 1, min(i + 5, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


# =============================================================================
# TRANCHE 10 (February 2026)
# =============================================================================

def _extract_cri_curbside_date(text: str) -> Optional[str]:
    """CRI Curbside - Columnar DATE header"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if line.strip().upper() == 'DATE':
            for j in range(i + 1, min(i + 5, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


def _extract_apex_waste_date(text: str) -> Optional[str]:
    """Apex Waste - NavuSoft DATE columnar with Month DD, YYYY format"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if line.strip().upper() == 'DATE':
            for j in range(i + 1, min(i + 5, len(lines))):
                # Month DD, YYYY format
                m = re.match(r'^\s*([A-Za-z]+)\s+(\d{1,2}),?\s*(\d{4})\s*$', lines[j].strip())
                if m:
                    month = MONTH_MAP.get(m.group(1).lower()[:3])
                    if month:
                        day, year = int(m.group(2)), int(m.group(3))
                        if _validate_date(month, day, year):
                            return _format_date(month, day, year)
                # Also try MM/DD/YYYY
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


def _extract_metalpro_date(text: str) -> Optional[str]:
    """Metalpro - Inline Credit Memo Date: or Ship Date:"""
    # Try Credit Memo Date first
    m = re.search(r'Credit\s+Memo\s+Date:\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})', text, re.IGNORECASE)
    if m:
        return _parse_date_match(m, 'MDY')
    # Try Ship Date
    m = re.search(r'Ship\s+Date:\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})', text, re.IGNORECASE)
    if m:
        return _parse_date_match(m, 'MDY')
    return None


def _extract_las_vegas_recycling_date(text: str) -> Optional[str]:
    """Las Vegas Recycling - Inline Invoice date:"""
    m = re.search(r'Invoice\s+date:\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})', text, re.IGNORECASE)
    if m:
        return _parse_date_match(m, 'MDY')
    return None


def _extract_edco_disposal_date(text: str) -> Optional[str]:
    """EDCO Disposal - Columnar Billing Date"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if 'BILLING DATE' in line.upper():
            for j in range(i + 1, min(i + 5, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


def _extract_interstate_waste_date(text: str) -> Optional[str]:
    """Interstate Waste - Inline Invoice Date:"""
    m = re.search(r'Invoice\s+Date:\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})', text, re.IGNORECASE)
    if m:
        return _parse_date_match(m, 'MDY')
    return None


def _extract_vls_environmental_date(text: str) -> Optional[str]:
    """VLS Environmental - Columnar Date: with DD-Mon-YYYY format on separate line"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if line.strip().upper().startswith('DATE:') or line.strip().upper() == 'DATE':
            # Check next few lines for DD-Mon-YYYY format
            for j in range(i + 1, min(i + 6, len(lines))):
                # DD-Mon-YYYY format (01-Jul-2025)
                m = re.match(r'^\s*(\d{1,2})-([A-Za-z]{3})-(\d{4})\s*$', lines[j].strip())
                if m:
                    day = int(m.group(1))
                    month = MONTH_MAP.get(m.group(2).lower()[:3])
                    year = int(m.group(3))
                    if month and _validate_date(month, day, year):
                        return _format_date(month, day, year)
                # Also try MM/DD/YYYY
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    # Fallback: inline Date: DD-Mon-YYYY
    m = re.search(r'Date:\s*(\d{1,2})-([A-Za-z]{3})-(\d{4})', text, re.IGNORECASE)
    if m:
        day = int(m.group(1))
        month = MONTH_MAP.get(m.group(2).lower()[:3])
        year = int(m.group(3))
        if month and _validate_date(month, day, year):
            return _format_date(month, day, year)
    return None


def _extract_aces_disposal_date(text: str) -> Optional[str]:
    """ACES Disposal - Inline Invoice Date:"""
    m = re.search(r'Invoice\s+Date:\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})', text, re.IGNORECASE)
    if m:
        return _parse_date_match(m, 'MDY')
    return None


def _extract_county_hauling_date(text: str) -> Optional[str]:
    """County Hauling - Columnar DATE header"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if line.strip().upper() == 'DATE':
            for j in range(i + 1, min(i + 5, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


def _extract_el_harvey_date(text: str) -> Optional[str]:
    """EL Harvey - NavuSoft STATEMENT DATE columnar"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if 'STATEMENT DATE' in line.upper():
            for j in range(i + 1, min(i + 6, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


def _extract_stevens_disposal_date(text: str) -> Optional[str]:
    """Stevens Disposal - Columnar Invoice Date"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if 'INVOICE DATE' in line.upper():
            for j in range(i + 1, min(i + 5, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


# =============================================================================
# TRANCHE 11 (February 2026)
# =============================================================================

def _extract_wasatch_waste_date(text: str) -> Optional[str]:
    """Wasatch Waste - FROM/TO service dates columnar, use FROM date"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if line.strip().upper() == 'FROM':
            # Date is 2 lines after FROM (after TO line)
            for j in range(i + 1, min(i + 4, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    # Fallback: inline FROM date
    m = re.search(r'FROM\s+(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})', text, re.IGNORECASE)
    if m:
        return _parse_date_match(m, 'MDY')
    # Also try D MON YYYY format (3 JUN 2025)
    m = re.search(r'(\d{1,2})\s+([A-Za-z]{3})\s+(\d{4})', text)
    if m:
        day = int(m.group(1))
        month = MONTH_MAP.get(m.group(2).lower()[:3])
        year = int(m.group(3))
        if month and _validate_date(month, day, year):
            return _format_date(month, day, year)
    return None


def _extract_texas_disposal_date(text: str) -> Optional[str]:
    """Texas Disposal - Columnar Date header"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if line.strip().upper() == 'DATE':
            for j in range(i + 1, min(i + 5, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


def _extract_atlas_disposal_date(text: str) -> Optional[str]:
    """Atlas Disposal - Inline Date: Mon D, YYYY format"""
    m = re.search(r'Date:\s*([A-Za-z]{3})\s+(\d{1,2}),?\s*(\d{4})', text, re.IGNORECASE)
    if m:
        month = MONTH_MAP.get(m.group(1).lower()[:3])
        if month:
            day, year = int(m.group(2)), int(m.group(3))
            if _validate_date(month, day, year):
                return _format_date(month, day, year)
    # Also try MM/DD/YYYY
    m = re.search(r'Date:\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})', text, re.IGNORECASE)
    if m:
        return _parse_date_match(m, 'MDY')
    return None


def _extract_boyas_recycling_date(text: str) -> Optional[str]:
    """Boyas Recycling - Columnar Invoice Date (values appear after multiple headers)"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if 'INVOICE DATE' in line.upper():
            # Search further down (values come after multiple header lines)
            for j in range(i + 1, min(i + 8, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


def _extract_nitti_sanitation_date(text: str) -> Optional[str]:
    """Nitti Sanitation - NavuSoft-style columnar DATE"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if line.strip().upper() == 'DATE':
            for j in range(i + 1, min(i + 5, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


def _extract_nexus_disposal_date(text: str) -> Optional[str]:
    """Nexus Disposal - Inline DATE: MM/DD/YY"""
    m = re.search(r'DATE:\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})', text, re.IGNORECASE)
    if m:
        return _parse_date_match(m, 'MDY')
    return None


def _extract_my_trash_date(text: str) -> Optional[str]:
    """My Trash (Smash My Trash) - Inline Invoice date:"""
    m = re.search(r'Invoice\s+date:\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})', text, re.IGNORECASE)
    if m:
        return _parse_date_match(m, 'MDY')
    return None


def _extract_mark_dunning_date(text: str) -> Optional[str]:
    """Mark Dunning - Columnar INV DATE"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if 'INV DATE' in line.upper():
            for j in range(i + 1, min(i + 5, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


def _extract_eco_tech_date(text: str) -> Optional[str]:
    """Eco-Tech - Columnar INV DATE"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if 'INV DATE' in line.upper():
            for j in range(i + 1, min(i + 5, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


def _extract_ace_recycling_date(text: str) -> Optional[str]:
    """Ace Recycling - NavuSoft DATE columnar with Month DD, YYYY"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if line.strip().upper() == 'DATE':
            for j in range(i + 1, min(i + 6, len(lines))):
                # Month DD, YYYY format
                m = re.match(r'^\s*([A-Za-z]+)\s+(\d{1,2}),?\s*(\d{4})\s*$', lines[j].strip())
                if m:
                    month = MONTH_MAP.get(m.group(1).lower()[:3])
                    if month:
                        day, year = int(m.group(2)), int(m.group(3))
                        if _validate_date(month, day, year):
                            return _format_date(month, day, year)
                # Also try MM/DD/YYYY
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


def _extract_heavenly_trash_date(text: str) -> Optional[str]:
    """Heavenly Trash (TrashBilling) - Weekday Mon DD, YYYY format"""
    # Pattern: Thu Feb 20, 2025
    m = re.search(r'(?:Mon|Tue|Wed|Thu|Fri|Sat|Sun)\s+([A-Za-z]{3})\s+(\d{1,2}),?\s*(\d{4})', text)
    if m:
        month = MONTH_MAP.get(m.group(1).lower()[:3])
        if month:
            day, year = int(m.group(2)), int(m.group(3))
            if _validate_date(month, day, year):
                return _format_date(month, day, year)
    return None


# =============================================================================
# TRANCHE 12 (February 2026)
# =============================================================================

def _extract_jp_mascaro_date(text: str) -> Optional[str]:
    """JP Mascaro - Columnar INVOICE DATE with Mon-DD-YY format"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if 'INVOICE DATE' in line.upper():
            # Check next few lines for Mon-DD-YY format
            for j in range(i + 1, min(i + 5, len(lines))):
                m = re.match(r'^\s*([A-Za-z]{3})-(\d{1,2})-(\d{2,4})\s*$', lines[j].strip())
                if m:
                    month = MONTH_MAP.get(m.group(1).lower()[:3])
                    if month:
                        day, year = int(m.group(2)), int(m.group(3))
                        if year < 100:
                            year = 2000 + year if year < 50 else 1900 + year
                        if _validate_date(month, day, year):
                            return _format_date(month, day, year)
                # Also try MM/DD/YYYY
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


def _extract_ram_waste_date(text: str) -> Optional[str]:
    """RAM Waste - NavuSoft STATEMENT DATE columnar format"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if 'STATEMENT DATE' in line.upper():
            for j in range(i + 1, min(i + 6, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


def _extract_valley_vista_date(text: str) -> Optional[str]:
    """Valley Vista - Invoice Period: start_date-end_date format (use start date)"""
    # Pattern: Invoice Period: 09/01/25-09/30/25 (use the first date)
    m = re.search(r'Invoice\s+Period:\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})', text, re.IGNORECASE)
    if m:
        return _parse_date_match(m, 'MDY')
    return None


def _extract_mountain_state_date(text: str) -> Optional[str]:
    """Mountain State Waste - Inline Date: Month DD, YYYY"""
    m = re.search(r'Date:\s*([A-Za-z]+)\s+(\d{1,2}),?\s*(\d{4})', text, re.IGNORECASE)
    if m:
        month = MONTH_MAP.get(m.group(1).lower()[:3])
        if month:
            day, year = int(m.group(2)), int(m.group(3))
            if _validate_date(month, day, year):
                return _format_date(month, day, year)
    # Also try MM/DD/YYYY
    m = re.search(r'Date:\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})', text, re.IGNORECASE)
    if m:
        return _parse_date_match(m, 'MDY')
    return None


def _extract_kmg_hauling_date(text: str) -> Optional[str]:
    """KMG Hauling - Columnar INVOICE DATE header"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if 'INVOICE DATE' in line.upper():
            for j in range(i + 1, min(i + 5, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


def _extract_gateway_disposal_date(text: str) -> Optional[str]:
    """Gateway Disposal - INV DATE: MM/DD/YY inline"""
    m = re.search(r'INV\s*DATE[:\s]+(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})', text, re.IGNORECASE)
    if m:
        return _parse_date_match(m, 'MDY')
    # Also try columnar
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if 'INV DATE' in line.upper():
            for j in range(i + 1, min(i + 5, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


def _extract_honolulu_disposal_date(text: str) -> Optional[str]:
    """Honolulu Disposal - Inline Date: M/DD/YY"""
    m = re.search(r'Date:\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})', text, re.IGNORECASE)
    if m:
        return _parse_date_match(m, 'MDY')
    return None


def _extract_ankeny_sanitation_date(text: str) -> Optional[str]:
    """Ankeny Sanitation - Inline Invoice Date: MM/DD/YYYY"""
    m = re.search(r'Invoice\s+Date:\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})', text, re.IGNORECASE)
    if m:
        return _parse_date_match(m, 'MDY')
    return None


def _extract_independent_recycling_date(text: str) -> Optional[str]:
    """Independent Recycling - Columnar DATE with Mon-DD-YY format"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if line.strip().upper() == 'DATE':
            # Check next few lines for Mon-DD-YY format
            for j in range(i + 1, min(i + 5, len(lines))):
                m = re.match(r'^\s*([A-Za-z]{3})-(\d{1,2})-(\d{2,4})\s*$', lines[j].strip())
                if m:
                    month = MONTH_MAP.get(m.group(1).lower()[:3])
                    if month:
                        day, year = int(m.group(2)), int(m.group(3))
                        if year < 100:
                            year = 2000 + year if year < 50 else 1900 + year
                        if _validate_date(month, day, year):
                            return _format_date(month, day, year)
                # Also try MM/DD/YYYY
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


def _extract_liberty_disposal_date(text: str) -> Optional[str]:
    """Liberty Disposal - Inline Date: Weekday Month DD, YYYY (Mon Mar 3, 2025)"""
    # Pattern: Date: Mon Mar 3, 2025
    m = re.search(r'Date:\s*(?:Mon|Tue|Wed|Thu|Fri|Sat|Sun)\s+([A-Za-z]+)\s+(\d{1,2}),?\s*(\d{4})', text, re.IGNORECASE)
    if m:
        month = MONTH_MAP.get(m.group(1).lower()[:3])
        if month:
            day, year = int(m.group(2)), int(m.group(3))
            if _validate_date(month, day, year):
                return _format_date(month, day, year)
    # Also try without weekday
    m = re.search(r'Date:\s*([A-Za-z]+)\s+(\d{1,2}),?\s*(\d{4})', text, re.IGNORECASE)
    if m:
        month = MONTH_MAP.get(m.group(1).lower()[:3])
        if month:
            day, year = int(m.group(2)), int(m.group(3))
            if _validate_date(month, day, year):
                return _format_date(month, day, year)
    # Fallback to MM/DD/YYYY
    m = re.search(r'Date:\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})', text, re.IGNORECASE)
    if m:
        return _parse_date_match(m, 'MDY')
    return None


# =============================================================================
# TRANCHE 13 (February 2026)
# =============================================================================

def _extract_live_oak_date(text: str) -> Optional[str]:
    """Live Oak - Columnar INVOICE DATE header"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if 'INVOICE DATE' in line.upper():
            for j in range(i + 1, min(i + 5, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


def _extract_zarc_recycling_date(text: str) -> Optional[str]:
    """ZARC Recycling - Inline Date: M/DD/YYYY"""
    m = re.search(r'Date:\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})', text, re.IGNORECASE)
    if m:
        return _parse_date_match(m, 'MDY')
    return None


def _extract_detroit_disposal_date(text: str) -> Optional[str]:
    """Detroit Disposal - Invoice Date in header block (M/D/YY format)"""
    # Pattern: Invoice Date followed by date on same line or nearby
    m = re.search(r'Invoice\s+Date\s+(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})', text, re.IGNORECASE)
    if m:
        return _parse_date_match(m, 'MDY')
    # Also try columnar
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if 'INVOICE DATE' in line.upper():
            for j in range(i + 1, min(i + 5, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


def _extract_all_american_waste_date(text: str) -> Optional[str]:
    """All American Waste - INVOICE DATE: MM/DD/YYYY inline"""
    m = re.search(r'INVOICE\s*DATE[:\s]+(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})', text, re.IGNORECASE)
    if m:
        return _parse_date_match(m, 'MDY')
    return None


def _extract_huntsville_hauling_date(text: str) -> Optional[str]:
    """Huntsville Hauling (Meridian) - Columnar Date header"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        # Look for standalone Date header
        if line.strip().upper() == 'DATE':
            for j in range(i + 1, min(i + 5, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    # Fallback: Date MM/DD/YYYY inline
    m = re.search(r'(?:^|\n)Date\s+(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})', text, re.IGNORECASE)
    if m:
        return _parse_date_match(m, 'MDY')
    return None


def _extract_amwaste_date(text: str) -> Optional[str]:
    """Amwaste - INVOICE DATE: MM/DD/YYYY inline"""
    m = re.search(r'INVOICE\s*DATE[:\s]+(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})', text, re.IGNORECASE)
    if m:
        return _parse_date_match(m, 'MDY')
    return None


def _extract_ghw_waste_date(text: str) -> Optional[str]:
    """GHW Waste - DATE DD-Mon-YYYY format (31-Jan-2025)"""
    # Pattern: DATE followed by DD-Mon-YYYY
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if line.strip().upper() == 'DATE':
            for j in range(i + 1, min(i + 5, len(lines))):
                # DD-Mon-YYYY format
                m = re.match(r'^\s*(\d{1,2})-([A-Za-z]{3})-(\d{4})\s*$', lines[j].strip())
                if m:
                    day = int(m.group(1))
                    month = MONTH_MAP.get(m.group(2).lower()[:3])
                    year = int(m.group(3))
                    if month and _validate_date(month, day, year):
                        return _format_date(month, day, year)
                # Also try MM/DD/YYYY
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    # Fallback: inline DD-Mon-YYYY
    m = re.search(r'(\d{1,2})-([A-Za-z]{3})-(\d{4})', text)
    if m:
        day = int(m.group(1))
        month = MONTH_MAP.get(m.group(2).lower()[:3])
        year = int(m.group(3))
        if month and _validate_date(month, day, year):
            return _format_date(month, day, year)
    return None


def _extract_grizzly_disposal_date(text: str) -> Optional[str]:
    """Grizzly Disposal (TrashBilling) - Weekday Month DD, YYYY format"""
    # Pattern: Wed May 21, 2025
    m = re.search(r'(?:Mon|Tue|Wed|Thu|Fri|Sat|Sun)\s+([A-Za-z]{3})\s+(\d{1,2}),?\s*(\d{4})', text)
    if m:
        month = MONTH_MAP.get(m.group(1).lower()[:3])
        if month:
            day, year = int(m.group(2)), int(m.group(3))
            if _validate_date(month, day, year):
                return _format_date(month, day, year)
    return None


def _extract_granger_waste_date(text: str) -> Optional[str]:
    """Granger Waste - Invoice Date: MM/DD/YYYY columnar"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if 'INVOICE DATE' in line.upper():
            for j in range(i + 1, min(i + 5, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


# =============================================================================
# TRANCHE 14 (February 2026)
# =============================================================================

def _extract_rdt_inc_date(text: str) -> Optional[str]:
    """RDT Inc (TrashBilling) - Weekday Month DD, YYYY format"""
    # Pattern: Tue Dec 31, 2024
    m = re.search(r'(?:Mon|Tue|Wed|Thu|Fri|Sat|Sun)\s+([A-Za-z]{3})\s+(\d{1,2}),?\s*(\d{4})', text)
    if m:
        month = MONTH_MAP.get(m.group(1).lower()[:3])
        if month:
            day, year = int(m.group(2)), int(m.group(3))
            if _validate_date(month, day, year):
                return _format_date(month, day, year)
    return None


def _extract_pete_pete_date(text: str) -> Optional[str]:
    """Pete & Pete - DATE: M/D/YY inline"""
    m = re.search(r'DATE:\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})', text, re.IGNORECASE)
    if m:
        return _parse_date_match(m, 'MDY')
    return None


def _extract_troiano_waste_date(text: str) -> Optional[str]:
    """Troiano Waste - INVOICE DATE columnar"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if 'INVOICE DATE' in line.upper():
            for j in range(i + 1, min(i + 5, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


def _extract_western_disposal_date(text: str) -> Optional[str]:
    """Western Disposal - Billing Date with dash-separated date (MM-DD-YYYY)"""
    # Pattern: Billing Date followed by date value
    m = re.search(r'Billing\s+Date\s+(\d{1,2})-(\d{1,2})-(\d{4})', text, re.IGNORECASE)
    if m:
        return _parse_date_match(m, 'MDY')
    # Also try columnar
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if 'BILLING DATE' in line.upper():
            for j in range(i + 1, min(i + 5, len(lines))):
                m = re.match(r'^\s*(\d{1,2})-(\d{1,2})-(\d{4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


def _extract_trash_taxi_date(text: str) -> Optional[str]:
    """Trash Taxi - 'received on' date format"""
    # Pattern: received on M/D/YYYY
    m = re.search(r'received on (\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})', text, re.IGNORECASE)
    if m:
        return _parse_date_match(m, 'MDY')
    # Also try TrashBilling format
    m = re.search(r'(?:Mon|Tue|Wed|Thu|Fri|Sat|Sun)\s+([A-Za-z]{3})\s+(\d{1,2}),?\s*(\d{4})', text)
    if m:
        month = MONTH_MAP.get(m.group(1).lower()[:3])
        if month:
            day, year = int(m.group(2)), int(m.group(3))
            if _validate_date(month, day, year):
                return _format_date(month, day, year)
    return None


def _extract_arrowaste_date(text: str) -> Optional[str]:
    """Arrowaste - Invoice Date: MM/DD/YYYY inline"""
    m = re.search(r'Invoice\s+Date:\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})', text, re.IGNORECASE)
    if m:
        return _parse_date_match(m, 'MDY')
    return None


def _extract_wise_environmental_date(text: str) -> Optional[str]:
    """Wise Environmental - NavuSoft DATE columnar with Month DD, YYYY"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if line.strip().upper() == 'DATE':
            for j in range(i + 1, min(i + 8, len(lines))):
                # Month DD, YYYY format
                m = re.match(r'^\s*([A-Za-z]+)\s+(\d{1,2}),?\s*(\d{4})\s*$', lines[j].strip())
                if m:
                    month = MONTH_MAP.get(m.group(1).lower()[:3])
                    if month:
                        day, year = int(m.group(2)), int(m.group(3))
                        if _validate_date(month, day, year):
                            return _format_date(month, day, year)
                # Also try MM/DD/YYYY
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


def _extract_nk_waste_date(text: str) -> Optional[str]:
    """NK Waste - DATE columnar"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if line.strip().upper() == 'DATE':
            for j in range(i + 1, min(i + 5, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


def _extract_blue_diamond_date(text: str) -> Optional[str]:
    """Blue Diamond Disposal - DATE columnar with Mon-DD-YY format"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if line.strip().upper() == 'DATE':
            for j in range(i + 1, min(i + 5, len(lines))):
                # Mon-DD-YY format (Nov-30-25)
                m = re.match(r'^\s*([A-Za-z]{3})-(\d{1,2})-(\d{2,4})\s*$', lines[j].strip())
                if m:
                    month = MONTH_MAP.get(m.group(1).lower()[:3])
                    if month:
                        day, year = int(m.group(2)), int(m.group(3))
                        if year < 100:
                            year = 2000 + year if year < 50 else 1900 + year
                        if _validate_date(month, day, year):
                            return _format_date(month, day, year)
                # Also try MM/DD/YYYY
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


def _extract_community_disposal_date(text: str) -> Optional[str]:
    """Community Disposal - DATE inline"""
    m = re.search(r'(?:^|\n)DATE\s+(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})', text, re.IGNORECASE)
    if m:
        return _parse_date_match(m, 'MDY')
    return None


# =============================================================================
# TRANCHE 15 (February 2026)
# =============================================================================

def _extract_basin_disposal_date(text: str) -> Optional[str]:
    """Basin Disposal - BILLING DATE: Month DD, YYYY inline"""
    m = re.search(r'BILLING\s+DATE:\s*([A-Za-z]+)\s+(\d{1,2}),?\s*(\d{4})', text, re.IGNORECASE)
    if m:
        month = MONTH_MAP.get(m.group(1).lower()[:3])
        if month:
            day, year = int(m.group(2)), int(m.group(3))
            if _validate_date(month, day, year):
                return _format_date(month, day, year)
    # Also try MM/DD/YYYY format
    m = re.search(r'BILLING\s+DATE:\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})', text, re.IGNORECASE)
    if m:
        return _parse_date_match(m, 'MDY')
    return None


def _extract_walker_lake_date(text: str) -> Optional[str]:
    """Walker Lake Disposal - Invoice date: MM/DD/YYYY inline"""
    m = re.search(r'Invoice\s+date:\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})', text, re.IGNORECASE)
    if m:
        return _parse_date_match(m, 'MDY')
    return None


def _extract_gulf_coast_date(text: str) -> Optional[str]:
    """Gulf Coast Containers - DATE columnar with Mon-DD-YY format"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if line.strip().upper() == 'DATE':
            for j in range(i + 1, min(i + 5, len(lines))):
                # Mon-DD-YY format (Nov-01-25)
                m = re.match(r'^\s*([A-Za-z]{3})-(\d{1,2})-(\d{2,4})\s*$', lines[j].strip())
                if m:
                    month = MONTH_MAP.get(m.group(1).lower()[:3])
                    if month:
                        day, year = int(m.group(2)), int(m.group(3))
                        if year < 100:
                            year = 2000 + year if year < 50 else 1900 + year
                        if _validate_date(month, day, year):
                            return _format_date(month, day, year)
                # Also try MM/DD/YYYY
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


def _extract_121_disposal_date(text: str) -> Optional[str]:
    """121 Disposal - Date inline M/D/YYYY"""
    m = re.search(r'(?:^|\n)Date\s+(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})', text, re.IGNORECASE)
    if m:
        return _parse_date_match(m, 'MDY')
    return None


def _extract_patriot_waste_date(text: str) -> Optional[str]:
    """Patriot Waste - DATE columnar"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if line.strip().upper() == 'DATE':
            for j in range(i + 1, min(i + 5, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


def _extract_solid_waste_authority_date(text: str) -> Optional[str]:
    """Solid Waste Authority - INVOICE DATE columnar"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if 'INVOICE DATE' in line.upper():
            for j in range(i + 1, min(i + 5, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


def _extract_velpen_trucking_date(text: str) -> Optional[str]:
    """Velpen Trucking (TrashBilling) - received on date format"""
    # Pattern: received on M/D/YYYY
    m = re.search(r'received on (\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})', text, re.IGNORECASE)
    if m:
        return _parse_date_match(m, 'MDY')
    # Also try TrashBilling format
    m = re.search(r'(?:Mon|Tue|Wed|Thu|Fri|Sat|Sun)\s+([A-Za-z]{3})\s+(\d{1,2}),?\s*(\d{4})', text)
    if m:
        month = MONTH_MAP.get(m.group(1).lower()[:3])
        if month:
            day, year = int(m.group(2)), int(m.group(3))
            if _validate_date(month, day, year):
                return _format_date(month, day, year)
    return None


def _extract_louisiana_waste_date(text: str) -> Optional[str]:
    """Louisiana Waste - NavuSoft DATE columnar with Mon D, YYYY format"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if line.strip().upper() == 'DATE':
            for j in range(i + 1, min(i + 8, len(lines))):
                # Mon D, YYYY format (Apr 1, 2025)
                m = re.match(r'^\s*([A-Za-z]+)\s+(\d{1,2}),?\s*(\d{4})\s*$', lines[j].strip())
                if m:
                    month = MONTH_MAP.get(m.group(1).lower()[:3])
                    if month:
                        day, year = int(m.group(2)), int(m.group(3))
                        if _validate_date(month, day, year):
                            return _format_date(month, day, year)
                # Also try MM/DD/YYYY
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


def _extract_renewable_resources_date(text: str) -> Optional[str]:
    """Renewable Resources - Invoice Date MM/DD/YYYY inline"""
    m = re.search(r'Invoice\s+Date\s+(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})', text, re.IGNORECASE)
    if m:
        return _parse_date_match(m, 'MDY')
    return None


# =============================================================================
# TRANCHE 16 (February 2026)
# =============================================================================

def _extract_lexington_site_date(text: str) -> Optional[str]:
    """Lexington Site Services - Billing Date Month DD, YYYY"""
    m = re.search(r'Billing\s+Date\s+([A-Za-z]+)\s+(\d{1,2}),?\s*(\d{4})', text, re.IGNORECASE)
    if m:
        month = MONTH_MAP.get(m.group(1).lower()[:3])
        if month:
            day, year = int(m.group(2)), int(m.group(3))
            if _validate_date(month, day, year):
                return _format_date(month, day, year)
    return None


def _extract_modern_recycling_date(text: str) -> Optional[str]:
    """Modern Recycling - Date: MM/DD/YY inline"""
    m = re.search(r'Date:\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})', text, re.IGNORECASE)
    if m:
        return _parse_date_match(m, 'MDY')
    return None


def _extract_wg_waste_date(text: str) -> Optional[str]:
    """WG Waste - INV DATE MM/DD/YY inline"""
    m = re.search(r'INV\s+DATE\s+(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})', text, re.IGNORECASE)
    if m:
        return _parse_date_match(m, 'MDY')
    return None


def _extract_boro_wide_date(text: str) -> Optional[str]:
    """Boro Wide - Invoice Date Month DD, YYYY"""
    m = re.search(r'Invoice\s+Date\s+([A-Za-z]+)\s+(\d{1,2}),?\s*(\d{4})', text, re.IGNORECASE)
    if m:
        month = MONTH_MAP.get(m.group(1).lower()[:3])
        if month:
            day, year = int(m.group(2)), int(m.group(3))
            if _validate_date(month, day, year):
                return _format_date(month, day, year)
    # Also try MM/DD/YYYY
    m = re.search(r'Invoice\s+Date\s+(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})', text, re.IGNORECASE)
    if m:
        return _parse_date_match(m, 'MDY')
    return None


def _extract_moore_coal_date(text: str) -> Optional[str]:
    """Moore Coal - DATE Mon-DD-YY columnar"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if line.strip().upper() == 'DATE':
            for j in range(i + 1, min(i + 5, len(lines))):
                # Mon-DD-YY format (Oct-31-25)
                m = re.match(r'^\s*([A-Za-z]{3})-(\d{1,2})-(\d{2,4})\s*$', lines[j].strip())
                if m:
                    month = MONTH_MAP.get(m.group(1).lower()[:3])
                    if month:
                        day, year = int(m.group(2)), int(m.group(3))
                        if year < 100:
                            year = 2000 + year if year < 50 else 1900 + year
                        if _validate_date(month, day, year):
                            return _format_date(month, day, year)
    return None


def _extract_curbside_date(text: str) -> Optional[str]:
    """Curbside Inc - Date: Month DD, YYYY inline"""
    m = re.search(r'Date:\s*([A-Za-z]+)\s+(\d{1,2}),?\s*(\d{4})', text, re.IGNORECASE)
    if m:
        month = MONTH_MAP.get(m.group(1).lower()[:3])
        if month:
            day, year = int(m.group(2)), int(m.group(3))
            if _validate_date(month, day, year):
                return _format_date(month, day, year)
    # Also try MM/DD/YYYY
    m = re.search(r'Date:\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})', text, re.IGNORECASE)
    if m:
        return _parse_date_match(m, 'MDY')
    return None


def _extract_redgate_disposal_date(text: str) -> Optional[str]:
    """Redgate Disposal - Date M/D/YYYY inline"""
    m = re.search(r'(?:^|\n)Date\s+(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})', text, re.IGNORECASE)
    if m:
        return _parse_date_match(m, 'MDY')
    return None


def _extract_1800_got_junk_date(text: str) -> Optional[str]:
    """1-800-Got-Junk - Date: MM/DD/YYYY inline"""
    m = re.search(r'Date:\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})', text, re.IGNORECASE)
    if m:
        return _parse_date_match(m, 'MDY')
    return None


def _extract_pelican_waste_date(text: str) -> Optional[str]:
    """Pelican Waste - Invoice Date MM/DD/YYYY"""
    m = re.search(r'Invoice\s+Date\s+(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})', text, re.IGNORECASE)
    if m:
        return _parse_date_match(m, 'MDY')
    return None


# =============================================================================
# TRANCHE 17 (February 2026)
# =============================================================================

def _extract_waste_away_date(text: str) -> Optional[str]:
    """Waste Away - Invoice Date columnar MM/DD/YYYY"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if 'INVOICE DATE' in line.upper():
            for j in range(i + 1, min(i + 5, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


def _extract_blue_hills_date(text: str) -> Optional[str]:
    """Blue Hills Environmental - Date Issued Month DD, YYYY"""
    text = _normalize_text(text)
    m = re.search(r'Date\s+Issued\s+([A-Za-z]+)\s+(\d{1,2}),?\s*(\d{4})', text, re.IGNORECASE)
    if m:
        month = MONTH_MAP.get(m.group(1).lower()[:3])
        if month:
            day, year = int(m.group(2)), int(m.group(3))
            if _validate_date(month, day, year):
                return _format_date(month, day, year)
    return None


def _extract_jlt_trucking_date(text: str) -> Optional[str]:
    """JLT Trucking - NavuSoft DATE Month DD, YYYY columnar"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if line.strip().upper() == 'DATE':
            for j in range(i + 1, min(i + 5, len(lines))):
                # Month DD, YYYY format
                m = re.match(r'^\s*([A-Za-z]+)\s+(\d{1,2}),?\s*(\d{4})\s*$', lines[j].strip())
                if m:
                    month = MONTH_MAP.get(m.group(1).lower()[:3])
                    if month:
                        day, year = int(m.group(2)), int(m.group(3))
                        if _validate_date(month, day, year):
                            return _format_date(month, day, year)
    return None


def _extract_ssw_frontload_date(text: str) -> Optional[str]:
    """SSW Frontload - TrashBilling 'received on' Weekday Mon DD, YYYY"""
    text = _normalize_text(text)
    m = re.search(r'received\s+on\s+(\d{1,2})/(\d{1,2})/(\d{4})', text, re.IGNORECASE)
    if m:
        return _parse_date_match(m, 'MDY')
    # Also try Mon DD, YYYY format
    m = re.search(r'received\s+on\s+(?:[A-Za-z]{3}\s+)?([A-Za-z]{3})\s+(\d{1,2}),?\s*(\d{4})', text, re.IGNORECASE)
    if m:
        month = MONTH_MAP.get(m.group(1).lower()[:3])
        if month:
            day, year = int(m.group(2)), int(m.group(3))
            if _validate_date(month, day, year):
                return _format_date(month, day, year)
    return None


def _extract_ace_waste_systems_date(text: str) -> Optional[str]:
    """Ace Waste Systems - Invoice Date: MM/DD/YYYY inline"""
    text = _normalize_text(text)
    m = re.search(r'Invoice\s+Date:\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})', text, re.IGNORECASE)
    if m:
        return _parse_date_match(m, 'MDY')
    return None


def _extract_stericycle_date(text: str) -> Optional[str]:
    """Stericycle - Invoice Date MM-DD-YYYY (dash-separated)"""
    text = _normalize_text(text)
    m = re.search(r'Invoice\s+Date\s+(\d{1,2})-(\d{1,2})-(\d{2,4})', text, re.IGNORECASE)
    if m:
        return _parse_date_match(m, 'MDY')
    # Also try with slash
    m = re.search(r'Invoice\s+Date\s+(\d{1,2})[/](\d{1,2})[/](\d{2,4})', text, re.IGNORECASE)
    if m:
        return _parse_date_match(m, 'MDY')
    return None


def _extract_trident_waste_date(text: str) -> Optional[str]:
    """Trident Waste - Date MM/DD/YYYY columnar"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if line.strip().upper() == 'DATE':
            for j in range(i + 1, min(i + 5, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


def _extract_abc_waste_date(text: str) -> Optional[str]:
    """ABC Waste - Date MM/DD/YYYY columnar"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if line.strip().upper() == 'DATE':
            for j in range(i + 1, min(i + 5, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


def _extract_cards_mo_date(text: str) -> Optional[str]:
    """Cards Mo - Date MM/DD/YYYY columnar"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if line.strip().upper() == 'DATE':
            for j in range(i + 1, min(i + 5, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


def _extract_west_central_date(text: str) -> Optional[str]:
    """West Central Sanitation - Billing Date MM/DD/YYYY columnar"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if 'BILLING DATE' in line.upper() and 'DUE' not in line.upper():
            # Headers on multiple lines, values follow later
            for j in range(i + 1, min(i + 10, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    # Fallback: inline pattern
    m = re.search(r'Billing\s+Date\s+(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})', text, re.IGNORECASE)
    if m:
        return _parse_date_match(m, 'MDY')
    return None


# =============================================================================
# TRANCHE 18 (February 2026)
# =============================================================================

def _extract_city_waste_date(text: str) -> Optional[str]:
    """City Waste - Invoice Date: MM/DD/YYYY inline"""
    text = _normalize_text(text)
    m = re.search(r'Invoice\s+Date:\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})', text, re.IGNORECASE)
    if m:
        return _parse_date_match(m, 'MDY')
    return None


def _extract_cwpm_date(text: str) -> Optional[str]:
    """CWPM - Invoice Date columnar MM/DD/YY"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if 'INVOICE DATE' in line.upper():
            for j in range(i + 1, min(i + 5, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


def _extract_roll_off_systems_date(text: str) -> Optional[str]:
    """Roll Off Systems - Invoice Date columnar MM/DD/YYYY"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if 'INVOICE DATE' in line.upper():
            for j in range(i + 1, min(i + 5, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


def _extract_tk_trash_date(text: str) -> Optional[str]:
    """TK Trash - Billing Date: MM/DD/YYYY inline"""
    text = _normalize_text(text)
    m = re.search(r'Billing\s+Date:\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})', text, re.IGNORECASE)
    if m:
        return _parse_date_match(m, 'MDY')
    return None


def _extract_corporate_services_date(text: str) -> Optional[str]:
    """Corporate Services Consultants - Date columnar M/D/YYYY"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if line.strip().upper() == 'DATE':
            for j in range(i + 1, min(i + 5, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


def _extract_abc_disposal_systems_date(text: str) -> Optional[str]:
    """ABC Disposal Systems - Date columnar MM/DD/YYYY"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if line.strip().upper() == 'DATE':
            for j in range(i + 1, min(i + 5, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


def _extract_vogel_disposal_date(text: str) -> Optional[str]:
    """Vogel Disposal - Invoice Date: MM/DD/YYYY inline"""
    text = _normalize_text(text)
    m = re.search(r'Invoice\s+Date:\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})', text, re.IGNORECASE)
    if m:
        return _parse_date_match(m, 'MDY')
    return None


def _extract_aaa_disposal_service_date(text: str) -> Optional[str]:
    """AAA Disposal Service - M/DD/YY inline (first date after Service Addr)"""
    text = _normalize_text(text)
    # Look for date pattern M/DD/YY or MM/DD/YY early in text
    m = re.search(r'(\d{1,2})[/\-](\d{1,2})[/\-](\d{2})\s', text)
    if m:
        return _parse_date_match(m, 'MDY')
    return None


def _extract_city_of_tucson_date(text: str) -> Optional[str]:
    """City of Tucson - Bill Date columnar MM/DD/YY"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if 'BILL DATE' in line.upper():
            for j in range(i, min(i + 3, len(lines))):
                m = re.search(r'(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})', lines[j])
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


def _extract_becker360_date(text: str) -> Optional[str]:
    """Becker360 - Document Date columnar Month DD, YYYY"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if 'DOCUMENT DATE' in line.upper():
            for j in range(i + 1, min(i + 3, len(lines))):
                # Month DD, YYYY format
                m = re.match(r'^\s*([A-Za-z]+)\s+(\d{1,2}),?\s*(\d{4})\s*$', lines[j].strip())
                if m:
                    month = MONTH_MAP.get(m.group(1).lower()[:3])
                    if month:
                        day, year = int(m.group(2)), int(m.group(3))
                        if _validate_date(month, day, year):
                            return _format_date(month, day, year)
    return None


# =============================================================================
# TRANCHE 19 (February 2026)
# =============================================================================

def _extract_clean_slate_date(text: str) -> Optional[str]:
    """Clean Slate - Payment Date columnar Month DD, YYYY"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if 'PAYMENT DATE' in line.upper():
            # Look for Month DD, YYYY pattern in following lines
            for j in range(i + 1, min(i + 8, len(lines))):
                m = re.match(r'^\s*([A-Za-z]+)\s+(\d{1,2}),?\s*(\d{4})\s*$', lines[j].strip())
                if m:
                    month = MONTH_MAP.get(m.group(1).lower()[:3])
                    if month:
                        day, year = int(m.group(2)), int(m.group(3))
                        if _validate_date(month, day, year):
                            return _format_date(month, day, year)
    return None


def _extract_wall_recycling_date(text: str) -> Optional[str]:
    """Wall Recycling - Date columnar MM/DD/YYYY"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if line.strip().upper() == 'DATE':
            for j in range(i + 1, min(i + 5, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


def _extract_total_reclaim_date(text: str) -> Optional[str]:
    """Total Reclaim - Invoice Date: MM/DD/YY inline"""
    text = _normalize_text(text)
    m = re.search(r'Invoice\s+Date\s*:\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})', text, re.IGNORECASE)
    if m:
        return _parse_date_match(m, 'MDY')
    return None


def _extract_dependable_sanitation_date(text: str) -> Optional[str]:
    """Dependable Sanitation - TrashBilling 'received on' format"""
    text = _normalize_text(text)
    m = re.search(r'received\s+on\s+(\d{1,2})/(\d{1,2})/(\d{4})', text, re.IGNORECASE)
    if m:
        return _parse_date_match(m, 'MDY')
    return None


def _extract_eoms_recycling_date(text: str) -> Optional[str]:
    """EOMS Recycling - Invoice + date Weekday Mon DD, YYYY"""
    text = _normalize_text(text)
    m = re.search(r'(?:^|\n)\s*([A-Za-z]{3})\s+([A-Za-z]{3})\s+(\d{1,2}),?\s*(\d{4})', text)
    if m:
        month = MONTH_MAP.get(m.group(2).lower()[:3])
        if month:
            day, year = int(m.group(3)), int(m.group(4))
            if _validate_date(month, day, year):
                return _format_date(month, day, year)
    return None


def _extract_kahut_waste_date(text: str) -> Optional[str]:
    """Kahut Waste - STATEMENT DATE columnar M/D/YYYY"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if 'STATEMENT DATE' in line.upper():
            for j in range(i + 1, min(i + 5, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


def _extract_modern_corporation_date(text: str) -> Optional[str]:
    """Modern Corporation - Date: MM/DD/YY inline"""
    text = _normalize_text(text)
    m = re.search(r'Date:\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})', text, re.IGNORECASE)
    if m:
        return _parse_date_match(m, 'MDY')
    return None


def _extract_ohio_valley_waste_date(text: str) -> Optional[str]:
    """Ohio Valley Waste - Invoice Date: MM/DD/YYYY inline"""
    text = _normalize_text(text)
    m = re.search(r'Invoice\s+Date:\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})', text, re.IGNORECASE)
    if m:
        return _parse_date_match(m, 'MDY')
    return None


def _extract_specialty_pallet_date(text: str) -> Optional[str]:
    """Specialty Pallet - Order Date columnar M/D/YYYY"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if 'ORDER DATE' in line.upper():
            for j in range(i + 1, min(i + 5, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


# =============================================================================
# TRANCHE 20 (February 2026)
# =============================================================================

def _extract_pennohio_date(text: str) -> Optional[str]:
    """Pennohio - INVOICE DATE columnar M/D/YYYY"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if 'INVOICE DATE' in line.upper():
            for j in range(i + 1, min(i + 5, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


def _extract_west_oahu_aggregate_date(text: str) -> Optional[str]:
    """West Oahu Aggregate - Invoice date: columnar MM/DD/YYYY"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if 'INVOICE DATE' in line.upper():
            for j in range(i + 1, min(i + 5, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


def _extract_heiberg_garbage_date(text: str) -> Optional[str]:
    """Heiberg Garbage - Closing Date columnar MM/DD/YY"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if 'CLOSING DATE' in line.upper():
            for j in range(i, min(i + 3, len(lines))):
                m = re.search(r'(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})', lines[j])
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


def _extract_county_waste_systems_date(text: str) -> Optional[str]:
    """County Waste Systems - Date columnar MM/DD/YYYY"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if line.strip().upper() == 'DATE':
            for j in range(i + 1, min(i + 5, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


def _extract_grace_hauling_date(text: str) -> Optional[str]:
    """Grace Hauling - INVOICE DATE MM/DD/YYYY inline"""
    text = _normalize_text(text)
    m = re.search(r'INVOICE\s+DATE\s+(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})', text, re.IGNORECASE)
    if m:
        return _parse_date_match(m, 'MDY')
    return None


def _extract_d_crescio_trucking_date(text: str) -> Optional[str]:
    """D Crescio Trucking - Date Mon D, YYYY inline"""
    text = _normalize_text(text)
    m = re.search(r'Date\s+([A-Za-z]+)\s+(\d{1,2}),?\s*(\d{4})', text, re.IGNORECASE)
    if m:
        month = MONTH_MAP.get(m.group(1).lower()[:3])
        if month:
            day, year = int(m.group(2)), int(m.group(3))
            if _validate_date(month, day, year):
                return _format_date(month, day, year)
    return None


def _extract_direct_waste_services_date(text: str) -> Optional[str]:
    """Direct Waste Services - INVOICE DATE columnar Mon D, YYYY"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if 'INVOICE DATE' in line.upper():
            for j in range(i + 1, min(i + 5, len(lines))):
                # Mon D, YYYY format
                m = re.match(r'^\s*([A-Za-z]+)\s+(\d{1,2}),?\s*(\d{4})\s*$', lines[j].strip())
                if m:
                    month = MONTH_MAP.get(m.group(1).lower()[:3])
                    if month:
                        day, year = int(m.group(2)), int(m.group(3))
                        if _validate_date(month, day, year):
                            return _format_date(month, day, year)
    return None


def _extract_jk_trash_date(text: str) -> Optional[str]:
    """J&K Trash - INV DATE MM/DD/YY columnar"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if 'INV DATE' in line.upper():
            for j in range(i + 1, min(i + 5, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


def _extract_junk_removed_now_date(text: str) -> Optional[str]:
    """Junk Removed Now - Date columnar Weekday Mon DD, YYYY"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if line.strip().upper() == 'DATE':
            for j in range(i + 1, min(i + 5, len(lines))):
                # Weekday Mon DD, YYYY format
                m = re.match(r'^\s*[A-Za-z]{3}\s+([A-Za-z]{3})\s+(\d{1,2}),?\s*(\d{4})\s*$', lines[j].strip())
                if m:
                    month = MONTH_MAP.get(m.group(1).lower()[:3])
                    if month:
                        day, year = int(m.group(2)), int(m.group(3))
                        if _validate_date(month, day, year):
                            return _format_date(month, day, year)
    return None


def _extract_atlantic_waste_date(text: str) -> Optional[str]:
    """Atlantic Waste - Invoice Date columnar M/DD/YY"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if 'INVOICE DATE' in line.upper():
            for j in range(i + 1, min(i + 5, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


def _extract_hill_country_waste_date(text: str) -> Optional[str]:
    """Hill Country Waste - TrashBilling 'received on' format"""
    text = _normalize_text(text)
    m = re.search(r'received\s+on\s+(\d{1,2})/(\d{1,2})/(\d{4})', text, re.IGNORECASE)
    if m:
        return _parse_date_match(m, 'MDY')
    return None


def _extract_florida_express_waste_date(text: str) -> Optional[str]:
    """Florida Express Waste - Statement Date columnar MM/DD/YYYY"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if 'STATEMENT DATE' in line.upper():
            for j in range(i + 1, min(i + 5, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


def _extract_community_waste_date(text: str) -> Optional[str]:
    """Community Waste - Invoice Date columnar MM/DD/YYYY"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if 'INVOICE DATE' in line.upper():
            for j in range(i + 1, min(i + 5, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


# =============================================================================
# TRANCHE 21 (February 2026)
# =============================================================================

def _extract_chrin_hauling_date(text: str) -> Optional[str]:
    """Chrin Hauling - INVOICE DATE columnar Mon D, YYYY"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if 'INVOICE DATE' in line.upper():
            for j in range(i + 1, min(i + 5, len(lines))):
                # Month D, YYYY format
                m = re.match(r'^\s*([A-Za-z]+)\s+(\d{1,2}),?\s*(\d{4})\s*$', lines[j].strip())
                if m:
                    month = MONTH_MAP.get(m.group(1).lower()[:3])
                    if month:
                        day, year = int(m.group(2)), int(m.group(3))
                        if _validate_date(month, day, year):
                            return _format_date(month, day, year)
    return None


def _extract_western_elite_date(text: str) -> Optional[str]:
    """Western Elite - Statement columnar Month DD, YYYY"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if line.strip().upper() == 'STATEMENT':
            for j in range(i + 1, min(i + 5, len(lines))):
                # Month DD, YYYY format
                m = re.match(r'^\s*([A-Za-z]+)\s+(\d{1,2}),?\s*(\d{4})\s*$', lines[j].strip())
                if m:
                    month = MONTH_MAP.get(m.group(1).lower()[:3])
                    if month:
                        day, year = int(m.group(2)), int(m.group(3))
                        if _validate_date(month, day, year):
                            return _format_date(month, day, year)
    return None


def _extract_willscot_date(text: str) -> Optional[str]:
    """WillScot - Invoice Date columnar M/D/YYYY (wide spacing)"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if 'INVOICE DATE' in line.upper():
            for j in range(i + 1, min(i + 10, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


def _extract_ryland_environmental_date(text: str) -> Optional[str]:
    """Ryland Environmental - Date: DD-Mon-YYYY inline"""
    text = _normalize_text(text)
    m = re.search(r'Date:\s*(\d{1,2})-([A-Za-z]{3})-(\d{4})', text, re.IGNORECASE)
    if m:
        day = int(m.group(1))
        month = MONTH_MAP.get(m.group(2).lower()[:3])
        year = int(m.group(3))
        if month and _validate_date(month, day, year):
            return _format_date(month, day, year)
    return None


def _extract_penn_waste_date(text: str) -> Optional[str]:
    """Penn Waste - Date: columnar M/D/YYYY (wide spacing)"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if line.strip().upper() == 'DATE:':
            for j in range(i + 1, min(i + 10, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


def _extract_thompson_sanitation_date(text: str) -> Optional[str]:
    """Thompson Sanitation - TrashBilling 'received on' format"""
    text = _normalize_text(text)
    m = re.search(r'received\s+on\s+(\d{1,2})/(\d{1,2})/(\d{4})', text, re.IGNORECASE)
    if m:
        return _parse_date_match(m, 'MDY')
    return None


def _extract_five_star_waste_date(text: str) -> Optional[str]:
    """Five Star Waste - DATE columnar MM/DD/YYYY (wide spacing)"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if line.strip().upper() == 'DATE':
            for j in range(i + 1, min(i + 10, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


def _extract_pellitteri_date(text: str) -> Optional[str]:
    """Pellitteri - Statement Weekday, Month DD, YYYY inline"""
    text = _normalize_text(text)
    m = re.search(r'(?:Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday),?\s+([A-Za-z]+)\s+(\d{1,2}),?\s*(\d{4})', text)
    if m:
        month = MONTH_MAP.get(m.group(1).lower()[:3])
        if month:
            day, year = int(m.group(2)), int(m.group(3))
            if _validate_date(month, day, year):
                return _format_date(month, day, year)
    return None


def _extract_great_waste_date(text: str) -> Optional[str]:
    """Great Waste - Invoice Date columnar M/DD/YY"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if 'INVOICE DATE' in line.upper():
            for j in range(i + 1, min(i + 5, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


def _extract_city_of_fargo_date(text: str) -> Optional[str]:
    """City of Fargo - DATE: columnar M/DD/YY"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if line.strip().upper() == 'DATE:':
            for j in range(i + 1, min(i + 5, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


# =============================================================================
# TRANCHE 22 (February 2026)
# =============================================================================

def _extract_cards_recycling_date(text: str) -> Optional[str]:
    """Cards Recycling - Date columnar MM/DD/YYYY"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if line.strip().upper() == 'DATE':
            for j in range(i + 1, min(i + 5, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


def _extract_dekalb_county_date(text: str) -> Optional[str]:
    """DeKalb County - Bill Date: MM/DD/YY inline"""
    text = _normalize_text(text)
    m = re.search(r'Bill\s+Date:\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})', text, re.IGNORECASE)
    if m:
        return _parse_date_match(m, 'MDY')
    return None


def _extract_sonnys_solid_waste_date(text: str) -> Optional[str]:
    """Sonny's Solid Waste - Date: Weekday Mon DD, YYYY inline"""
    text = _normalize_text(text)
    m = re.search(r'Date:\s*(?:[A-Za-z]{3}\s+)?([A-Za-z]{3})\s+(\d{1,2}),?\s*(\d{4})', text, re.IGNORECASE)
    if m:
        month = MONTH_MAP.get(m.group(1).lower()[:3])
        if month:
            day, year = int(m.group(2)), int(m.group(3))
            if _validate_date(month, day, year):
                return _format_date(month, day, year)
    return None


def _extract_waste_services_llc_date(text: str) -> Optional[str]:
    """Waste Services LLC - Invoice Date columnar M/D/YYYY"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if 'INVOICE D' in line.upper():
            for j in range(i + 1, min(i + 5, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


def _extract_southern_sanitation_date(text: str) -> Optional[str]:
    """Southern Sanitation - DATE columnar MM/DD/YYYY"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if line.strip().upper() == 'DATE':
            for j in range(i + 1, min(i + 5, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


def _extract_greif_date(text: str) -> Optional[str]:
    """Greif - Transfer Date columnar MM-DD-YYYY"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if 'TRANSFER DATE' in line.upper():
            for j in range(i + 1, min(i + 5, len(lines))):
                m = re.match(r'^\s*(\d{1,2})-(\d{1,2})-(\d{4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


def _extract_orlando_waste_paper_date(text: str) -> Optional[str]:
    """Orlando Waste Paper - INV DATE MM/DD/YY columnar"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if 'INV DATE' in line.upper():
            for j in range(i + 1, min(i + 5, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


def _extract_gotta_go_waste_date(text: str) -> Optional[str]:
    """Gotta Go Waste - Date columnar MM/DD/YYYY"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if line.strip().upper() == 'DATE':
            for j in range(i + 1, min(i + 8, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


# =============================================================================
# TRANCHE 23 (February 2026)
# =============================================================================

def _extract_tfc_recycling_date(text: str) -> Optional[str]:
    """TFC Recycling - Date columnar M/D/YYYY"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if line.strip().upper() == 'DATE':
            for j in range(i + 1, min(i + 5, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


def _extract_premier_waste_date(text: str) -> Optional[str]:
    """Premier Waste - STATEMENT DATE columnar MM/DD/YY (wide spacing)"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if 'STATEMENT DATE' in line.upper():
            for j in range(i + 1, min(i + 10, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


def _extract_richardson_waste_date(text: str) -> Optional[str]:
    """Richardson Waste - Date columnar MM/DD/YYYY (wide spacing)"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if line.strip().upper() == 'DATE':
            for j in range(i + 1, min(i + 8, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


def _extract_waste_path_date(text: str) -> Optional[str]:
    """Waste Path - DATE label appears AFTER date value (line above)"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if line.strip().upper() == 'DATE':
            # Date value is on the line BEFORE the DATE label
            for j in range(max(0, i - 3), i):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


def _extract_indiana_waste_date(text: str) -> Optional[str]:
    """Indiana Waste - INV DATE columnar MM/DD/YY"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if 'INV DATE' in line.upper():
            for j in range(i + 1, min(i + 5, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


def _extract_city_of_jackson_date(text: str) -> Optional[str]:
    """City of Jackson - BILL DATE columnar MM/DD/YYYY (wide spacing)"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if 'BILL DATE' in line.upper():
            for j in range(i + 1, min(i + 10, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


def _extract_green_guys_date(text: str) -> Optional[str]:
    """Green Guys - Payment Date columnar DD Mon YYYY"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if 'PAYMENT DATE' in line.upper():
            for j in range(i + 1, min(i + 5, len(lines))):
                m = re.match(r'^\s*(\d{1,2})\s+([A-Za-z]{3})\s+(\d{4})\s*$', lines[j].strip())
                if m:
                    day = int(m.group(1))
                    month = MONTH_MAP.get(m.group(2).lower()[:3])
                    year = int(m.group(3))
                    if month and _validate_date(month, day, year):
                        return _format_date(month, day, year)
    return None


def _extract_texas_pride_disposal_date(text: str) -> Optional[str]:
    """Texas Pride Disposal - Invoice Date columnar MM/DD/YYYY"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if 'INVOICE DATE' in line.upper():
            for j in range(i + 1, min(i + 5, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


def _extract_all_metals_recycling_date(text: str) -> Optional[str]:
    """All Metals Recycling - Date columnar M/DD/YYYY"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if line.strip().upper() == 'DATE':
            for j in range(i + 1, min(i + 5, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


def _extract_advance_machine_date(text: str) -> Optional[str]:
    """Advance Machine & Hydraulic - Invoice date: inline MM/DD/YYYY"""
    text = _normalize_text(text)
    m = re.search(r'Invoice\s+date:\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})', text, re.IGNORECASE)
    if m:
        return _parse_date_match(m, 'MDY')
    return None


def _extract_city_of_blackfoot_date(text: str) -> Optional[str]:
    """City of Blackfoot - DUE DATE columnar MM/DD/YY (wide spacing)"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if 'DUE DATE' in line.upper():
            for j in range(i + 1, min(i + 10, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


def _extract_city_of_boise_date(text: str) -> Optional[str]:
    """City of Boise - Statement Date: inline MM/DD/YYYY"""
    text = _normalize_text(text)
    m = re.search(r'Statement\s+Date:\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})', text, re.IGNORECASE)
    if m:
        return _parse_date_match(m, 'MDY')
    return None


# =============================================================================
# TRANCHE 24 (February 2026)
# =============================================================================

def _extract_circle_sanitation_date(text: str) -> Optional[str]:
    """Circle Sanitation - Date columnar M/D/YYYY"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if line.strip().upper() == 'DATE':
            for j in range(i + 1, min(i + 5, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


def _extract_uribe_refuse_date(text: str) -> Optional[str]:
    """Uribe Refuse - DATE header, dates in detail rows MM/DD/YYYY"""
    text = _normalize_text(text)
    lines = text.split('\n')
    # Look for dates in format MM/DD/YYYY in the detail rows
    for line in lines:
        m = re.match(r'^\s*(\d{2})[/\-](\d{2})[/\-](\d{4})\s+', line)
        if m:
            return _parse_date_match(m, 'MDY')
    return None


def _extract_conex_recycling_date(text: str) -> Optional[str]:
    """Conex Recycling - DATE columnar M/D/YYYY"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if line.strip().upper() == 'DATE':
            for j in range(i + 1, min(i + 5, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


def _extract_roosevelt_ut_date(text: str) -> Optional[str]:
    """Roosevelt UT - BILLING DATE columnar MM/DD/YYYY"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if 'BILLING DATE' in line.upper():
            for j in range(i + 1, min(i + 5, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


def _extract_cleeton_sanitation_date(text: str) -> Optional[str]:
    """Cleeton Sanitation - BILLING PERIOD: Month, YYYY inline"""
    text = _normalize_text(text)
    m = re.search(r'BILLING\s+PERIOD:\s*([A-Za-z]+),?\s*(\d{4})', text, re.IGNORECASE)
    if m:
        month = MONTH_MAP.get(m.group(1).lower()[:3])
        year = int(m.group(2))
        if month:
            return _format_date(month, 1, year)
    return None


def _extract_intermountain_disposal_date(text: str) -> Optional[str]:
    """Intermountain Disposal - Date columnar M/D/YYYY"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if line.strip().upper() == 'DATE':
            for j in range(i + 1, min(i + 5, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


def _extract_ag_logistics_date(text: str) -> Optional[str]:
    """AG Logistics - DATE inline MM/DD/YYYY"""
    text = _normalize_text(text)
    m = re.search(r'\bDATE\s+(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})', text, re.IGNORECASE)
    if m:
        return _parse_date_match(m, 'MDY')
    return None


def _extract_pride_disposal_date(text: str) -> Optional[str]:
    """PRIDE Disposal - INV. DATE columnar MM/DD/YYYY (wide spacing)"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if 'INV. DATE' in line.upper() or 'INV DATE' in line.upper():
            for j in range(i + 1, min(i + 10, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


def _extract_cavossa_disposal_date(text: str) -> Optional[str]:
    """Cavossa Disposal - ACCOUNT SUMMARY AS OF MM/DD/YYYY inline"""
    text = _normalize_text(text)
    m = re.search(r'ACCOUNT\s+SUMMARY\s+AS\s+OF\s+(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})', text, re.IGNORECASE)
    if m:
        return _parse_date_match(m, 'MDY')
    return None


def _extract_royal_document_date(text: str) -> Optional[str]:
    """Royal Document Destruction - Services through MM/DD/YYYY inline"""
    text = _normalize_text(text)
    m = re.search(r'Services\s+through\s+(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})', text, re.IGNORECASE)
    if m:
        return _parse_date_match(m, 'MDY')
    return None


def _extract_lawrence_county_date(text: str) -> Optional[str]:
    """Lawrence County Solid Waste - Invoice Date: inline MM/DD/YYYY"""
    text = _normalize_text(text)
    m = re.search(r'Invoice\s+Date:\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})', text, re.IGNORECASE)
    if m:
        return _parse_date_match(m, 'MDY')
    return None


def _extract_bruin_waste_date(text: str) -> Optional[str]:
    """Bruin Waste Management - INVOICE DATE columnar Month DD, YYYY"""
    text = _normalize_text(text)
    lines = text.split('\n')
    # Look for Month DD, YYYY format near top
    for line in lines[:15]:
        m = re.match(r'^\s*([A-Za-z]{3,})\s+(\d{1,2}),?\s*(\d{4})\s*$', line.strip())
        if m:
            month = MONTH_MAP.get(m.group(1).lower()[:3])
            if month:
                day, year = int(m.group(2)), int(m.group(3))
                if _validate_date(month, day, year):
                    return _format_date(month, day, year)
    return None


# =============================================================================
# TRANCHE 25 - February 2026
# =============================================================================

def _extract_city_of_meridian_date(text: str) -> Optional[str]:
    """City of Meridian - Date: inline MM/DD/YYYY"""
    text = _normalize_text(text)
    # Pattern: Date: 10/05/2025
    m = re.search(r'Date:\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})', text, re.IGNORECASE)
    if m:
        return _parse_date_match(m, 'MDY')
    return None


def _extract_black_hawk_waste_date(text: str) -> Optional[str]:
    """Black Hawk Waste - Date columnar MM/DD/YYYY"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if line.strip().lower() == 'date':
            for j in range(i + 1, min(i + 5, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


def _extract_crp_sanitation_date(text: str) -> Optional[str]:
    """CRP Sanitation - DATE columnar Mon-DD-YY (Sep-27-25)"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if line.strip().upper() == 'DATE':
            for j in range(i + 1, min(i + 8, len(lines))):
                # Mon-DD-YY format
                m = re.match(r'^\s*([A-Za-z]{3})-(\d{1,2})-(\d{2,4})\s*$', lines[j].strip())
                if m:
                    month = MONTH_MAP.get(m.group(1).lower())
                    if month:
                        day, year = int(m.group(2)), int(m.group(3))
                        if year < 100:
                            year = 2000 + year if year < 50 else 1900 + year
                        if _validate_date(month, day, year):
                            return _format_date(month, day, year)
    return None


def _extract_salandro_refuse_date(text: str) -> Optional[str]:
    """Salandro Refuse - Invoice Date columnar MM/DD/YYYY"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if 'invoice date' in line.lower() and 'due date' not in line.lower():
            for j in range(i + 1, min(i + 10, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


def _extract_city_of_deerfield_beach_date(text: str) -> Optional[str]:
    """City of Deerfield Beach - DATE columnar MM/DD/YYYY"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if line.strip().upper() == 'DATE':
            for j in range(i + 1, min(i + 8, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


def _extract_olympic_compactor_date(text: str) -> Optional[str]:
    """Olympic Compactor Rentals - INVOICE DATE: columnar M/D/YYYY"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if 'invoice date' in line.lower():
            for j in range(i + 1, min(i + 5, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


def _extract_dunham_date(text: str) -> Optional[str]:
    """Dunham - Invoice Date: inline MM/DD/YYYY"""
    text = _normalize_text(text)
    m = re.search(r'Invoice\s+Date:\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})', text, re.IGNORECASE)
    if m:
        return _parse_date_match(m, 'MDY')
    return None


def _extract_city_of_nampa_date(text: str) -> Optional[str]:
    """City of Nampa - Statement Date columnar M/DD/YYYY"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if 'statement date' in line.lower():
            for j in range(i + 1, min(i + 3, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


def _extract_pascon_date(text: str) -> Optional[str]:
    """Pascon - Date columnar MM/DD/YYYY"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if line.strip().lower() == 'date':
            for j in range(i + 1, min(i + 5, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


def _extract_rockwood_sustainable_date(text: str) -> Optional[str]:
    """Rockwood Sustainable Solutions - DATE label, Mon-DD-YY reverse columnar (value before label)"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if line.strip().upper() == 'DATE':
            # Look backwards for date value
            for j in range(max(0, i - 5), i):
                # Mon-DD-YY format
                m = re.match(r'^\s*([A-Za-z]{3})-(\d{1,2})-(\d{2,4})\s*$', lines[j].strip())
                if m:
                    month = MONTH_MAP.get(m.group(1).lower())
                    if month:
                        day, year = int(m.group(2)), int(m.group(3))
                        if year < 100:
                            year = 2000 + year if year < 50 else 1900 + year
                        if _validate_date(month, day, year):
                            return _format_date(month, day, year)
    return None


def _extract_jt_environmental_date(text: str) -> Optional[str]:
    """J&T Environmental - Date columnar M/D/YYYY"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if line.strip().lower() == 'date':
            for j in range(i + 1, min(i + 3, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


def _extract_cooks_wastepaper_date(text: str) -> Optional[str]:
    """Cooks Wastepaper - STATEMENT DATE columnar MM/DD/YY"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if 'statement date' in line.lower():
            for j in range(i + 1, min(i + 7, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


def _extract_southern_illinois_waste_date(text: str) -> Optional[str]:
    """Southern Illinois Waste - Date columnar M/D/YYYY (wide spacing)"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if line.strip().lower() == 'date':
            for j in range(i + 1, min(i + 10, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


def _extract_geodom_carting_date(text: str) -> Optional[str]:
    """Geodom Carting - DATE columnar MM/DD/YYYY"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if line.strip().upper() == 'DATE':
            for j in range(i + 1, min(i + 5, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


def _extract_g2_revolution_date(text: str) -> Optional[str]:
    """G2 Revolution - Invoice date: inline MM/DD/YYYY"""
    text = _normalize_text(text)
    # Try inline pattern first
    m = re.search(r'Invoice\s+[Dd]ate[:\s]+(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})', text)
    if m:
        return _parse_date_match(m, 'MDY')
    return None


def _extract_all_florida_scrap_metals_date(text: str) -> Optional[str]:
    """All Florida Scrap Metals - Invoice Date inline MM/DD/YYYY"""
    text = _normalize_text(text)
    m = re.search(r'Invoice\s+Date\s+(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})', text, re.IGNORECASE)
    if m:
        return _parse_date_match(m, 'MDY')
    return None


def _extract_jettison_environmental_date(text: str) -> Optional[str]:
    """Jettison Environmental - INVOICE DATE columnar MM/DD/YY or MM/DD/YYYY"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if 'invoice date' in line.lower() and 'due date' not in line.lower():
            for j in range(i + 1, min(i + 8, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


def _extract_udp_tn_hauling_date(text: str) -> Optional[str]:
    """UDP TN Hauling - INVOICE DATE reverse columnar MM/DD/YYYY (value before label)"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if 'invoice date' in line.lower():
            # Look backwards for date value (it's on the line BEFORE the label)
            for j in range(max(0, i - 3), i):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


def _extract_the_trash_man_date(text: str) -> Optional[str]:
    """The Trash Man (TrashBilling) - Weekday Month DD, YYYY format"""
    text = _normalize_text(text)
    # Pattern: Thu May 1, 2025
    m = re.search(r'(?:Mon|Tue|Wed|Thu|Fri|Sat|Sun)\s+([A-Za-z]{3,})\s+(\d{1,2}),?\s*(\d{4})', text)
    if m:
        month = MONTH_MAP.get(m.group(1).lower()[:3])
        if month:
            day, year = int(m.group(2)), int(m.group(3))
            if _validate_date(month, day, year):
                return _format_date(month, day, year)
    return None


def _extract_tri_city_disposal_date(text: str) -> Optional[str]:
    """Tri-City Disposal (TrashBilling) - Weekday Month DD, YYYY format"""
    text = _normalize_text(text)
    # Pattern: Thu May 15, 2025
    m = re.search(r'(?:Mon|Tue|Wed|Thu|Fri|Sat|Sun)\s+([A-Za-z]{3,})\s+(\d{1,2}),?\s*(\d{4})', text)
    if m:
        month = MONTH_MAP.get(m.group(1).lower()[:3])
        if month:
            day, year = int(m.group(2)), int(m.group(3))
            if _validate_date(month, day, year):
                return _format_date(month, day, year)
    return None


def _extract_hoss_disposal_date(text: str) -> Optional[str]:
    """Hoss Disposal - MM/DD/YY date in early lines (no clear label)"""
    text = _normalize_text(text)
    lines = text.split('\n')
    # Look for date in first 10 lines
    for line in lines[:10]:
        m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2})\s*$', line.strip())
        if m:
            return _parse_date_match(m, 'MDY')
    return None


def _extract_am_disposal_date(text: str) -> Optional[str]:
    """AM Disposal - Issue date columnar Month DD, YYYY"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if 'issue date' in line.lower():
            for j in range(i + 1, min(i + 3, len(lines))):
                # Month DD, YYYY format
                m = re.match(r'^\s*([A-Za-z]{3,})\s+(\d{1,2}),?\s*(\d{4})\s*$', lines[j].strip())
                if m:
                    month = MONTH_MAP.get(m.group(1).lower()[:3])
                    if month:
                        day, year = int(m.group(2)), int(m.group(3))
                        if _validate_date(month, day, year):
                            return _format_date(month, day, year)
    return None


def _extract_northern_waste_date(text: str) -> Optional[str]:
    """Northern Waste - INVOICE DATE columnar MM/DD/YYYY"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if 'invoice date' in line.lower():
            for j in range(i + 1, min(i + 5, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


def _extract_burgmeiers_hauling_date(text: str) -> Optional[str]:
    """Burgmeier's Hauling - INV DATE columnar MM/DD/YY"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if 'inv date' in line.lower():
            for j in range(i + 1, min(i + 3, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


def _extract_sunrise_sanitation_service_date(text: str) -> Optional[str]:
    """Sunrise Sanitation Service - Date columnar M/D/YYYY"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if line.strip().lower() == 'date':
            for j in range(i + 1, min(i + 5, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


def _extract_c_d_disposal_date(text: str) -> Optional[str]:
    """C & D Disposal - Invoice Date columnar MM/DD/YY"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if 'invoice date' in line.lower():
            # Look in nearby lines for dates
            for j in range(max(0, i - 3), min(i + 5, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


def _extract_first_piedmont_date(text: str) -> Optional[str]:
    """First Piedmont - INVOICE DATE: columnar M/DD/YY"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if 'invoice date' in line.lower():
            for j in range(i + 1, min(i + 3, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


# =============================================================================
# TRANCHE 26 - February 2026
# =============================================================================

def _extract_mid_valley_disposal_date(text: str) -> Optional[str]:
    """Mid Valley Disposal - Invoice Date columnar M/DD/YY"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if 'invoice date' in line.lower():
            for j in range(i + 1, min(i + 3, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


def _extract_kootenai_county_date(text: str) -> Optional[str]:
    """Kootenai County Solid Waste - Bill Date: inline MM/DD/YYYY"""
    text = _normalize_text(text)
    m = re.search(r'Bill\s+Date:\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})', text, re.IGNORECASE)
    if m:
        return _parse_date_match(m, 'MDY')
    return None


def _extract_bcc_waste_date(text: str) -> Optional[str]:
    """BCC Waste Solutions - INVOICE DATE columnar M/D/YYYY"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if 'invoice date' in line.lower():
            for j in range(i + 1, min(i + 3, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


def _extract_schaap_sanitation_date(text: str) -> Optional[str]:
    """Schaap Sanitation - STATEMENT DATE columnar M/D/YYYY"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if 'statement date' in line.lower():
            for j in range(i + 1, min(i + 3, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


def _extract_amber_disposal_date(text: str) -> Optional[str]:
    """Amber Disposal - INV DATE columnar MM/DD/YY"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if 'inv date' in line.lower():
            for j in range(i + 1, min(i + 3, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


def _extract_appalachian_waste_date(text: str) -> Optional[str]:
    """Appalachian Waste Management - INVOICE/DATE reverse columnar MM/DD/YYYY"""
    text = _normalize_text(text)
    lines = text.split('\n')
    # Look for INVOICE followed by DATE on next line
    for i, line in enumerate(lines):
        if line.strip().upper() == 'INVOICE' and i + 1 < len(lines):
            if lines[i + 1].strip().upper() == 'DATE':
                # Date is BEFORE INVOICE label
                for j in range(max(0, i - 3), i):
                    m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                    if m:
                        return _parse_date_match(m, 'MDY')
    return None


def _extract_f_l_construction_date(text: str) -> Optional[str]:
    """F & L Construction - DATE columnar DD-Mon-YYYY"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if line.strip().upper() == 'DATE':
            for j in range(i + 1, min(i + 3, len(lines))):
                # DD-Mon-YYYY format (01-Mar-2025)
                m = re.match(r'^\s*(\d{1,2})-([A-Za-z]{3})-(\d{4})\s*$', lines[j].strip())
                if m:
                    day = int(m.group(1))
                    month = MONTH_MAP.get(m.group(2).lower())
                    year = int(m.group(3))
                    if month and _validate_date(month, day, year):
                        return _format_date(month, day, year)
    return None


def _extract_vista_recycling_date(text: str) -> Optional[str]:
    """Vista Recycling - Invoice Date columnar M/D/YY"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if 'invoice date' in line.lower():
            for j in range(i + 1, min(i + 3, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


def _extract_martin_environmental_date(text: str) -> Optional[str]:
    """Martin Environmental - Invoice Date columnar MM/DD/YYYY"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if 'invoice date' in line.lower():
            for j in range(i + 1, min(i + 5, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


def _extract_rich_county_date(text: str) -> Optional[str]:
    """Rich County - Date columnar MM/DD/YYYY"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if line.strip().lower() == 'date':
            for j in range(i + 1, min(i + 3, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


def _extract_pop_and_son_date(text: str) -> Optional[str]:
    """Pop and Son Trucking - Issue date columnar Month DD, YYYY"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if 'issue date' in line.lower():
            for j in range(i + 1, min(i + 3, len(lines))):
                m = re.match(r'^\s*([A-Za-z]{3,})\s+(\d{1,2}),?\s*(\d{4})\s*$', lines[j].strip())
                if m:
                    month = MONTH_MAP.get(m.group(1).lower()[:3])
                    if month:
                        day, year = int(m.group(2)), int(m.group(3))
                        if _validate_date(month, day, year):
                            return _format_date(month, day, year)
    return None


def _extract_at_disposal_date(text: str) -> Optional[str]:
    """AT Disposal - Date columnar MM/DD/YYYY"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if line.strip().lower() == 'date':
            for j in range(i + 1, min(i + 5, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


def _extract_waste_pro_oregon_date(text: str) -> Optional[str]:
    """Waste Pro Oregon - BILL DATE: Month DD, YYYY"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if 'bill date' in line.lower():
            for j in range(i + 1, min(i + 3, len(lines))):
                m = re.match(r'^\s*([A-Za-z]+)\s+(\d{1,2}),?\s*(\d{4})\s*$', lines[j].strip())
                if m:
                    month = MONTH_MAP.get(m.group(1).lower()[:3])
                    if month:
                        day, year = int(m.group(2)), int(m.group(3))
                        if _validate_date(month, day, year):
                            return _format_date(month, day, year)
    return None


def _extract_mission_trail_date(text: str) -> Optional[str]:
    """Mission Trail Waste - INV. DATE columnar M/DD/YYYY"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if 'inv. date' in line.lower() or 'inv date' in line.lower():
            for j in range(i + 1, min(i + 8, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


def _extract_hart_sanitation_date(text: str) -> Optional[str]:
    """Hart Sanitation (TrashBilling) - received on M/DD/YYYY"""
    text = _normalize_text(text)
    m = re.search(r'received\s+on\s+(\d{1,2})[/\-](\d{1,2})[/\-](\d{4})', text, re.IGNORECASE)
    if m:
        return _parse_date_match(m, 'MDY')
    return None


def _extract_disposal_services_llc_date(text: str) -> Optional[str]:
    """Disposal Services LLC (TrashBilling) - received on M/DD/YYYY"""
    text = _normalize_text(text)
    m = re.search(r'received\s+on\s+(\d{1,2})[/\-](\d{1,2})[/\-](\d{4})', text, re.IGNORECASE)
    if m:
        return _parse_date_match(m, 'MDY')
    return None


def _extract_ozark_disposal_date(text: str) -> Optional[str]:
    """Ozark Disposal (TrashBilling) - received on M/DD/YYYY"""
    text = _normalize_text(text)
    m = re.search(r'received\s+on\s+(\d{1,2})[/\-](\d{1,2})[/\-](\d{4})', text, re.IGNORECASE)
    if m:
        return _parse_date_match(m, 'MDY')
    return None


def _extract_maricks_waste_date(text: str) -> Optional[str]:
    """Marick's Waste Disposal (TrashBilling) - received on M/DD/YYYY"""
    text = _normalize_text(text)
    m = re.search(r'received\s+on\s+(\d{1,2})[/\-](\d{1,2})[/\-](\d{4})', text, re.IGNORECASE)
    if m:
        return _parse_date_match(m, 'MDY')
    return None


def _extract_city_of_bardstown_date(text: str) -> Optional[str]:
    """City of Bardstown (Bluegrass Junk) - ISSUED ON columnar DD Mon YYYY"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if 'issued on' in line.lower():
            for j in range(i + 1, min(i + 3, len(lines))):
                # DD Mon YYYY format (26 Nov 2025)
                m = re.match(r'^\s*(\d{1,2})\s+([A-Za-z]{3})\s+(\d{4})\s*$', lines[j].strip())
                if m:
                    day = int(m.group(1))
                    month = MONTH_MAP.get(m.group(2).lower())
                    year = int(m.group(3))
                    if month and _validate_date(month, day, year):
                        return _format_date(month, day, year)
    return None


# =============================================================================
# TRANCHE 27 - February 2026
# =============================================================================

def _extract_garden_isle_disposal_date(text: str) -> Optional[str]:
    """Garden Isle Disposal - DATE/NUMBER header, MM/DD/YYYY value below"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if line.strip().upper() == 'DATE':
            for j in range(i + 1, min(i + 10, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


def _extract_ontario_municipal_date(text: str) -> Optional[str]:
    """Ontario Municipal - Bill Date: inline M/D/YYYY"""
    text = _normalize_text(text)
    m = re.search(r'Bill\s+Date:\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})', text, re.IGNORECASE)
    if m:
        return _parse_date_match(m, 'MDY')
    return None


def _extract_allstate_equipment_date(text: str) -> Optional[str]:
    """Allstate Equipment Services - DATE columnar MM/DD/YYYY"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if line.strip().upper() == 'DATE':
            for j in range(i + 1, min(i + 3, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


def _extract_pete_and_pete_date(text: str) -> Optional[str]:
    """Pete and Pete - INVOICE DATE columnar MM/DD/YYYY"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if 'invoice date' in line.lower():
            for j in range(i + 1, min(i + 5, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


def _extract_quality_waste_date(text: str) -> Optional[str]:
    """Quality Waste - DATE columnar DD-Mon-YYYY"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if line.strip().upper() == 'DATE':
            for j in range(i + 1, min(i + 3, len(lines))):
                # DD-Mon-YYYY format (30-Jun-2025)
                m = re.match(r'^\s*(\d{1,2})-([A-Za-z]{3})-(\d{4})\s*$', lines[j].strip())
                if m:
                    day = int(m.group(1))
                    month = MONTH_MAP.get(m.group(2).lower())
                    year = int(m.group(3))
                    if month and _validate_date(month, day, year):
                        return _format_date(month, day, year)
    return None


def _extract_reliable_sanitation_date(text: str) -> Optional[str]:
    """Reliable Sanitation (TrashBilling) - received on M/DD/YYYY"""
    text = _normalize_text(text)
    m = re.search(r'received\s+on\s+(\d{1,2})[/\-](\d{1,2})[/\-](\d{4})', text, re.IGNORECASE)
    if m:
        return _parse_date_match(m, 'MDY')
    return None


def _extract_grogan_waste_date(text: str) -> Optional[str]:
    """Grogan Waste - DATE inline MM/DD/YYYY"""
    text = _normalize_text(text)
    m = re.search(r'DATE\s+(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})', text, re.IGNORECASE)
    if m:
        return _parse_date_match(m, 'MDY')
    return None


def _extract_efficient_rolloff_date(text: str) -> Optional[str]:
    """Efficient Roll-Off & Recycling - Date columnar M/DD/YYYY"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if line.strip().lower() == 'date':
            for j in range(i + 1, min(i + 5, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


def _extract_sanitary_service_company_date(text: str) -> Optional[str]:
    """Sanitary Service Company - Billing Date: inline M/D/YY"""
    text = _normalize_text(text)
    m = re.search(r'Billing\s+Date:\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})', text, re.IGNORECASE)
    if m:
        return _parse_date_match(m, 'MDY')
    return None


def _extract_miami_dade_dswm_date(text: str) -> Optional[str]:
    """Miami-Dade DSWM - Invoice Date columnar M/DD/YY"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if 'invoice date' in line.lower():
            for j in range(i + 1, min(i + 5, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


def _extract_bp_trucking_date(text: str) -> Optional[str]:
    """BP Trucking - INVOICE DATE columnar Mon-DD-YY"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if 'invoice date' in line.lower():
            for j in range(i + 1, min(i + 3, len(lines))):
                # Mon-DD-YY format (Jul-01-25)
                m = re.match(r'^\s*([A-Za-z]{3})-(\d{1,2})-(\d{2,4})\s*$', lines[j].strip())
                if m:
                    month = MONTH_MAP.get(m.group(1).lower())
                    if month:
                        day, year = int(m.group(2)), int(m.group(3))
                        if year < 100:
                            year = 2000 + year if year < 50 else 1900 + year
                        if _validate_date(month, day, year):
                            return _format_date(month, day, year)
    return None


def _extract_kern_county_date(text: str) -> Optional[str]:
    """Kern County Public Works - INVOICE DATE: inline MM/DD/YYYY"""
    text = _normalize_text(text)
    m = re.search(r'INVOICE\s+DATE:\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})', text, re.IGNORECASE)
    if m:
        return _parse_date_match(m, 'MDY')
    return None


# =============================================================================
# TRANCHE 28 - February 2026
# =============================================================================

def _extract_ll_site_services_date(text: str) -> Optional[str]:
    """L&L Site Services (TrashBilling) - Weekday Month DD, YYYY"""
    text = _normalize_text(text)
    m = re.search(r'(?:Mon|Tue|Wed|Thu|Fri|Sat|Sun)\s+([A-Za-z]{3,})\s+(\d{1,2}),?\s*(\d{4})', text)
    if m:
        month = MONTH_MAP.get(m.group(1).lower()[:3])
        if month:
            day, year = int(m.group(2)), int(m.group(3))
            if _validate_date(month, day, year):
                return _format_date(month, day, year)
    return None


def _extract_earthwise_waste_date(text: str) -> Optional[str]:
    """Earthwise Waste Solutions (TrashBilling) - Weekday Month DD, YYYY"""
    text = _normalize_text(text)
    m = re.search(r'(?:Mon|Tue|Wed|Thu|Fri|Sat|Sun)\s+([A-Za-z]{3,})\s+(\d{1,2}),?\s*(\d{4})', text)
    if m:
        month = MONTH_MAP.get(m.group(1).lower()[:3])
        if month:
            day, year = int(m.group(2)), int(m.group(3))
            if _validate_date(month, day, year):
                return _format_date(month, day, year)
    return None


def _extract_island_disposal_date(text: str) -> Optional[str]:
    """Island Disposal - Invoice date: columnar MM/DD/YYYY"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if 'invoice date' in line.lower():
            for j in range(i + 1, min(i + 8, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


def _extract_lusk_disposal_date(text: str) -> Optional[str]:
    """Lusk Disposal - DATE columnar MM/DD/YYYY"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if line.strip().upper() == 'DATE':
            for j in range(i + 1, min(i + 5, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


def _extract_pro_waste_services_date(text: str) -> Optional[str]:
    """Pro Waste Services - Invoice Date columnar MM/DD/YYYY"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if 'invoice date' in line.lower():
            for j in range(i + 1, min(i + 8, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


def _extract_major_waste_date(text: str) -> Optional[str]:
    """Major Waste - Payment date columnar MM/DD/YYYY"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if 'payment date' in line.lower():
            for j in range(i + 1, min(i + 8, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


def _extract_arts_garbage_date(text: str) -> Optional[str]:
    """Art's Garbage - STATEMENT DATE columnar MM/DD/YY"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if 'statement date' in line.lower():
            for j in range(i + 1, min(i + 8, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


def _extract_midwest_sanitation_date(text: str) -> Optional[str]:
    """Midwest Sanitation - Date on line after account number M/D/YY"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if 'billing acct no' in line.lower():
            for j in range(i + 1, min(i + 3, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


def _extract_hometown_sanitation_date(text: str) -> Optional[str]:
    """Hometown Sanitation - Date columnar Mon-DD-YY"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if line.strip().lower() == 'date':
            for j in range(i + 1, min(i + 8, len(lines))):
                # Mon-DD-YY format (Jan-01-26)
                m = re.match(r'^\s*([A-Za-z]{3})-(\d{1,2})-(\d{2,4})\s*$', lines[j].strip())
                if m:
                    month = MONTH_MAP.get(m.group(1).lower())
                    if month:
                        day, year = int(m.group(2)), int(m.group(3))
                        if year < 100:
                            year = 2000 + year if year < 50 else 1900 + year
                        if _validate_date(month, day, year):
                            return _format_date(month, day, year)
    return None


def _extract_marborg_date(text: str) -> Optional[str]:
    """Marborg - Invoice Date columnar MM/DD/YYYY"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if 'invoice date' in line.lower():
            for j in range(i + 1, min(i + 3, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


def _extract_sage_disposal_date(text: str) -> Optional[str]:
    """Sage Disposal - Date: inline Month DD, YYYY"""
    text = _normalize_text(text)
    m = re.search(r'Date:\s*([A-Za-z]{3,})\s+(\d{1,2}),?\s*(\d{4})', text, re.IGNORECASE)
    if m:
        month = MONTH_MAP.get(m.group(1).lower()[:3])
        if month:
            day, year = int(m.group(2)), int(m.group(3))
            if _validate_date(month, day, year):
                return _format_date(month, day, year)
    return None


def _extract_mid_south_waste_date(text: str) -> Optional[str]:
    """Mid South Waste - Date MM-DD-YY in early lines"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for line in lines[:10]:
        m = re.match(r'^\s*(\d{1,2})-(\d{1,2})-(\d{2,4})\s*$', line.strip())
        if m:
            return _parse_date_match(m, 'MDY')
    return None


def _extract_lk_specialties_date(text: str) -> Optional[str]:
    """LK Specialties - Date columnar M/D/YYYY"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if line.strip().lower() == 'date':
            for j in range(i + 1, min(i + 5, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


def _extract_complete_solutions_date(text: str) -> Optional[str]:
    """Complete Solutions & Sourcing - Date columnar M/D/YYYY"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if line.strip().lower() == 'date':
            for j in range(i + 1, min(i + 5, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


def _extract_city_of_pembroke_pines_date(text: str) -> Optional[str]:
    """City of Pembroke Pines - BILL DATE columnar MM/DD/YYYY"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if 'bill date' in line.lower():
            for j in range(i + 1, min(i + 8, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


# =============================================================================
# TRANCHE 29 - February 2026
# =============================================================================

def _extract_rad_curbside_date(text: str) -> Optional[str]:
    """RAD Curbside - Payment date columnar MM/DD/YYYY"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if 'payment date' in line.lower():
            for j in range(i + 1, min(i + 8, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


def _extract_american_waste_control_date(text: str) -> Optional[str]:
    """American Waste Control - INVOICE DATE columnar Month DD, YYYY"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if 'invoice date' in line.lower():
            for j in range(i + 1, min(i + 5, len(lines))):
                m = re.match(r'^\s*([A-Za-z]{3,})\s+(\d{1,2}),?\s*(\d{4})\s*$', lines[j].strip())
                if m:
                    month = MONTH_MAP.get(m.group(1).lower()[:3])
                    if month:
                        day, year = int(m.group(2)), int(m.group(3))
                        if _validate_date(month, day, year):
                            return _format_date(month, day, year)
    return None


def _extract_absolute_waste_date(text: str) -> Optional[str]:
    """Absolute Waste - Invoice Date: inline MM/DD/YYYY"""
    text = _normalize_text(text)
    m = re.search(r'Invoice\s+Date:\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})', text, re.IGNORECASE)
    if m:
        return _parse_date_match(m, 'MDY')
    return None


def _extract_pak_rite_rentals_date(text: str) -> Optional[str]:
    """Pak Rite Rentals - Invoice date columnar MM/DD/YY (wide spacing)"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if 'invoice date' in line.lower():
            for j in range(i + 1, min(i + 15, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


def _extract_bliss_environmental_date(text: str) -> Optional[str]:
    """Bliss Environmental (TrashBilling) - Weekday Month DD, YYYY"""
    text = _normalize_text(text)
    m = re.search(r'(?:Mon|Tue|Wed|Thu|Fri|Sat|Sun)\s+([A-Za-z]{3,})\s+(\d{1,2}),?\s*(\d{4})', text)
    if m:
        month = MONTH_MAP.get(m.group(1).lower()[:3])
        if month:
            day, year = int(m.group(2)), int(m.group(3))
            if _validate_date(month, day, year):
                return _format_date(month, day, year)
    return None


def _extract_south_tahoe_refuse_date(text: str) -> Optional[str]:
    """South Tahoe Refuse - Statement Date columnar MM/DD/YYYY"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if 'statement date' in line.lower():
            for j in range(i + 1, min(i + 5, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


def _extract_haul_away_rubbish_date(text: str) -> Optional[str]:
    """Haul Away Rubbish - INV DATE columnar MM/DD/YY"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if 'inv date' in line.lower():
            for j in range(i + 1, min(i + 3, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


def _extract_trashco_date(text: str) -> Optional[str]:
    """TRASHCO - Invoice Date: inline MM/DD/YYYY"""
    text = _normalize_text(text)
    m = re.search(r'Invoice\s+Date:\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})', text, re.IGNORECASE)
    if m:
        return _parse_date_match(m, 'MDY')
    return None


def _extract_green_obky_date(text: str) -> Optional[str]:
    """Green OBKY - DATE inline MM/DD/YYYY"""
    text = _normalize_text(text)
    m = re.search(r'DATE\s+(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})', text, re.IGNORECASE)
    if m:
        return _parse_date_match(m, 'MDY')
    return None


def _extract_csd_disposal_date(text: str) -> Optional[str]:
    """CSD Disposal - Invoice Date columnar MM/DD/YY"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if 'invoice date' in line.lower():
            for j in range(i + 1, min(i + 8, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


def _extract_rapid_removal_date(text: str) -> Optional[str]:
    """Rapid Removal (TrashBilling) - Weekday Month DD, YYYY"""
    text = _normalize_text(text)
    m = re.search(r'(?:Mon|Tue|Wed|Thu|Fri|Sat|Sun)\s+([A-Za-z]{3,})\s+(\d{1,2}),?\s*(\d{4})', text)
    if m:
        month = MONTH_MAP.get(m.group(1).lower()[:3])
        if month:
            day, year = int(m.group(2)), int(m.group(3))
            if _validate_date(month, day, year):
                return _format_date(month, day, year)
    return None


def _extract_cram_a_lot_date(text: str) -> Optional[str]:
    """Cram-A-Lot - Invoice Date: inline MM/DD/YY"""
    text = _normalize_text(text)
    m = re.search(r'Invoice\s+Date:\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})', text, re.IGNORECASE)
    if m:
        return _parse_date_match(m, 'MDY')
    return None


# =============================================================================
# TRANCHE 30 - February 2026
# =============================================================================

def _extract_grand_rapids_iron_date(text: str) -> Optional[str]:
    """Grand Rapids Iron - Invoice Date: inline MM/DD/YYYY"""
    text = _normalize_text(text)
    m = re.search(r'Invoice\s+Date:\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})', text, re.IGNORECASE)
    if m:
        return _parse_date_match(m, 'MDY')
    return None


def _extract_cards_ks_date(text: str) -> Optional[str]:
    """Cards KS - Date columnar MM/DD/YYYY"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if line.strip().lower() == 'date':
            for j in range(i + 1, min(i + 5, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


def _extract_diamond_disposal_date(text: str) -> Optional[str]:
    """Diamond Disposal - Invoice date: inline MM/DD/YYYY"""
    text = _normalize_text(text)
    m = re.search(r'Invoice\s+date:\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})', text, re.IGNORECASE)
    if m:
        return _parse_date_match(m, 'MDY')
    return None


def _extract_trash_control_date(text: str) -> Optional[str]:
    """Trash Control - Invoice Date: inline Month DD, YYYY"""
    text = _normalize_text(text)
    m = re.search(r'Invoice\s+Date:\s*([A-Za-z]{3,})\s+(\d{1,2}),?\s*(\d{4})', text, re.IGNORECASE)
    if m:
        month = MONTH_MAP.get(m.group(1).lower()[:3])
        if month:
            day, year = int(m.group(2)), int(m.group(3))
            if _validate_date(month, day, year):
                return _format_date(month, day, year)
    return None


def _extract_engebretson_sons_date(text: str) -> Optional[str]:
    """Engebretson & Sons - STATEMENT DATE columnar MM/DD/YY"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if 'statement date' in line.lower():
            for j in range(i + 1, min(i + 8, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


def _extract_k_town_disposal_date(text: str) -> Optional[str]:
    """K-Town Disposal - INVOICE DATE columnar Month DD, YYYY"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if 'invoice date' in line.lower():
            for j in range(i + 1, min(i + 8, len(lines))):
                m = re.match(r'^\s*([A-Za-z]+)\s+(\d{1,2}),?\s*(\d{4})\s*$', lines[j].strip())
                if m:
                    month = MONTH_MAP.get(m.group(1).lower()[:3])
                    if month:
                        day, year = int(m.group(2)), int(m.group(3))
                        if _validate_date(month, day, year):
                            return _format_date(month, day, year)
    return None


def _extract_basin_haulage_date(text: str) -> Optional[str]:
    """Basin Haulage - Invoice Date: columnar Month DD, YYYY"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if 'invoice date' in line.lower():
            for j in range(i + 1, min(i + 3, len(lines))):
                m = re.match(r'^\s*([A-Za-z]{3,})\s+(\d{1,2}),?\s*(\d{4})\s*$', lines[j].strip())
                if m:
                    month = MONTH_MAP.get(m.group(1).lower()[:3])
                    if month:
                        day, year = int(m.group(2)), int(m.group(3))
                        if _validate_date(month, day, year):
                            return _format_date(month, day, year)
    return None


def _extract_suburban_waste_services_date(text: str) -> Optional[str]:
    """Suburban Waste Services - INVOICE DATE reverse columnar Mon-DD-YY"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if 'invoice date' in line.lower():
            # Look backwards for Mon-DD-YY format
            for j in range(max(0, i - 5), i):
                m = re.match(r'^\s*([A-Za-z]{3})-(\d{1,2})-(\d{2,4})\s*$', lines[j].strip())
                if m:
                    month = MONTH_MAP.get(m.group(1).lower())
                    if month:
                        day, year = int(m.group(2)), int(m.group(3))
                        if year < 100:
                            year = 2000 + year if year < 50 else 1900 + year
                        if _validate_date(month, day, year):
                            return _format_date(month, day, year)
    return None


def _extract_a1_disposal_date(text: str) -> Optional[str]:
    """A-1 Disposal - Date columnar M/DD/YYYY"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if line.strip().lower() == 'date':
            for j in range(i + 1, min(i + 8, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


def _extract_advance_disposal_date(text: str) -> Optional[str]:
    """Advance Disposal - Invoice date: columnar MM/DD/YYYY"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if 'invoice date' in line.lower():
            for j in range(i + 1, min(i + 8, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


def _extract_ns_disposal_date(text: str) -> Optional[str]:
    """NS Disposal - Invoice Date: columnar Month DD, YYYY"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if 'invoice date' in line.lower():
            for j in range(i + 1, min(i + 3, len(lines))):
                m = re.match(r'^\s*([A-Za-z]{3,})\s+(\d{1,2}),?\s*(\d{4})\s*$', lines[j].strip())
                if m:
                    month = MONTH_MAP.get(m.group(1).lower()[:3])
                    if month:
                        day, year = int(m.group(2)), int(m.group(3))
                        if _validate_date(month, day, year):
                            return _format_date(month, day, year)
    return None


def _extract_mcgree_trucking_date(text: str) -> Optional[str]:
    """McGree Trucking - Date columnar MM/DD/YYYY"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if line.strip().lower() == 'date':
            for j in range(i + 1, min(i + 5, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


def _extract_updike_industries_date(text: str) -> Optional[str]:
    """Updike Industries - Date columnar MM/DD/YYYY"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if line.strip().lower() == 'date':
            for j in range(i + 1, min(i + 8, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


def _extract_green_planet_21_date(text: str) -> Optional[str]:
    """Green Planet 21 - Invoice date Mon DD, YYYY on separate line"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for line in lines[:15]:
        # Look for Month DD, YYYY standalone
        m = re.match(r'^\s*([A-Za-z]{3,})\s+(\d{1,2}),?\s*(\d{4})\s*$', line.strip())
        if m:
            month = MONTH_MAP.get(m.group(1).lower()[:3])
            if month:
                day, year = int(m.group(2)), int(m.group(3))
                if _validate_date(month, day, year):
                    return _format_date(month, day, year)
    return None


# =============================================================================
# TRANCHE 31 - February 2026
# =============================================================================

def _extract_pacific_waste_date(text: str) -> Optional[str]:
    """Pacific Waste - Total Due By columnar MM/DD/YYYY"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if 'total due by' in line.lower():
            for j in range(i + 1, min(i + 5, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


def _extract_river_parish_disposal_date(text: str) -> Optional[str]:
    """River Parish Disposal - DATE(MM/DD/YYYY) columnar"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if 'date' in line.lower() and 'mm/dd' in line.lower():
            for j in range(i + 1, min(i + 5, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


def _extract_mikes_rubbish_date(text: str) -> Optional[str]:
    """Mike's Rubbish - Date: Weekday Month DD, YYYY (TrashBilling)"""
    text = _normalize_text(text)
    m = re.search(r'Date:\s*(?:Mon|Tue|Wed|Thu|Fri|Sat|Sun)\s+([A-Za-z]{3,})\s+(\d{1,2}),?\s*(\d{4})', text, re.IGNORECASE)
    if m:
        month = MONTH_MAP.get(m.group(1).lower()[:3])
        if month:
            day, year = int(m.group(2)), int(m.group(3))
            if _validate_date(month, day, year):
                return _format_date(month, day, year)
    return None


def _extract_ej_harrison_sons_date(text: str) -> Optional[str]:
    """E.J. Harrison & Sons - DATE columnar M/DD/YY in billing section"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if line.strip().upper() == 'DATE':
            # Look for M/DD/YY or MM/DD/YY in next several lines
            for j in range(i + 1, min(i + 15, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


def _extract_city_of_sherman_date(text: str) -> Optional[str]:
    """City of Sherman - BILL DATE: inline MM/DD/YYYY"""
    text = _normalize_text(text)
    m = re.search(r'BILL\s+DATE:\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})', text, re.IGNORECASE)
    if m:
        return _parse_date_match(m, 'MDY')
    return None


def _extract_waste_zero_date(text: str) -> Optional[str]:
    """Waste Zero - DATE columnar MM/DD/YYYY"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if line.strip().upper() == 'DATE':
            for j in range(i + 1, min(i + 5, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


def _extract_hugill_sanitation_date(text: str) -> Optional[str]:
    """Hugill Sanitation - Weekday Month DD, YYYY (TrashBilling)"""
    text = _normalize_text(text)
    m = re.search(r'(?:Mon|Tue|Wed|Thu|Fri|Sat|Sun)\s+([A-Za-z]{3,})\s+(\d{1,2}),?\s*(\d{4})', text)
    if m:
        month = MONTH_MAP.get(m.group(1).lower()[:3])
        if month:
            day, year = int(m.group(2)), int(m.group(3))
            if _validate_date(month, day, year):
                return _format_date(month, day, year)
    return None


def _extract_3r_technology_date(text: str) -> Optional[str]:
    """3R Technology - MM/DD/YYYY standalone after INVOICE label"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if 'invoice' in line.lower() and 'inv-' not in line.lower():
            for j in range(i + 1, min(i + 8, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


def _extract_tri_county_industries_date(text: str) -> Optional[str]:
    """Tri-County Industries - Invoice Date: inline MM/DD/YYYY"""
    text = _normalize_text(text)
    m = re.search(r'Invoice\s+Date:\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})', text, re.IGNORECASE)
    if m:
        return _parse_date_match(m, 'MDY')
    return None


def _extract_city_of_tulsa_date(text: str) -> Optional[str]:
    """City of Tulsa - Account Summary MM/DD/YYYY to MM/DD/YYYY"""
    text = _normalize_text(text)
    m = re.search(r'Account\s+Summary\s+(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})', text, re.IGNORECASE)
    if m:
        return _parse_date_match(m, 'MDY')
    return None


def _extract_apex_recycling_disposal_date(text: str) -> Optional[str]:
    """Apex Recycling & Disposal - STATEMENT DATE columnar MM/DD/YYYY (wide spacing)"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if 'statement date' in line.lower():
            # Date can be on same line, next few lines, or 6+ lines down (header format)
            for j in range(i, min(i + 10, len(lines))):
                m = re.search(r'(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})', lines[j])
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


def _extract_hmp_inc_date(text: str) -> Optional[str]:
    """HMP Inc - DATE columnar MM/DD/YYYY"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if line.strip().upper() == 'DATE':
            for j in range(i + 1, min(i + 3, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


def _extract_ssw_box_services_date(text: str) -> Optional[str]:
    """SSW-Box Services - Weekday Month DD, YYYY (TrashBilling)"""
    text = _normalize_text(text)
    m = re.search(r'(?:Mon|Tue|Wed|Thu|Fri|Sat|Sun)\s+([A-Za-z]{3,})\s+(\d{1,2}),?\s*(\d{4})', text)
    if m:
        month = MONTH_MAP.get(m.group(1).lower()[:3])
        if month:
            day, year = int(m.group(2)), int(m.group(3))
            if _validate_date(month, day, year):
                return _format_date(month, day, year)
    return None


def _extract_hillside_solutions_date(text: str) -> Optional[str]:
    """Hillside Solutions - DATE MM/DD/YYYY inline"""
    text = _normalize_text(text)
    m = re.search(r'DATE\s+(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})', text, re.IGNORECASE)
    if m:
        return _parse_date_match(m, 'MDY')
    return None


# =============================================================================
# TRANCHE 32 - February 2026
# =============================================================================

def _extract_whitecap_waste_date(text: str) -> Optional[str]:
    """Whitecap Waste - DATE columnar Month DD, YYYY (NavuSoft)"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if line.strip().upper() == 'DATE':
            for j in range(i + 1, min(i + 5, len(lines))):
                m = re.match(r'^\s*([A-Za-z]{3,})\s+(\d{1,2}),?\s*(\d{4})\s*$', lines[j].strip())
                if m:
                    month = MONTH_MAP.get(m.group(1).lower()[:3])
                    if month:
                        day, year = int(m.group(2)), int(m.group(3))
                        if _validate_date(month, day, year):
                            return _format_date(month, day, year)
    return None


def _extract_jims_sanitation_date(text: str) -> Optional[str]:
    """Jim's Sanitation - Date columnar M/D/YYYY"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if line.strip().lower() == 'date':
            for j in range(i + 1, min(i + 8, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


def _extract_r_local_sanitation_date(text: str) -> Optional[str]:
    """R-Local Sanitation - Weekday Month DD, YYYY (TrashBilling)"""
    text = _normalize_text(text)
    m = re.search(r'(?:Mon|Tue|Wed|Thu|Fri|Sat|Sun)\s+([A-Za-z]{3,})\s+(\d{1,2}),?\s*(\d{4})', text)
    if m:
        month = MONTH_MAP.get(m.group(1).lower()[:3])
        if month:
            day, year = int(m.group(2)), int(m.group(3))
            if _validate_date(month, day, year):
                return _format_date(month, day, year)
    return None


def _extract_prestige_disposal_date(text: str) -> Optional[str]:
    """Prestige Disposal - Weekday Month DD, YYYY (TrashBilling)"""
    text = _normalize_text(text)
    m = re.search(r'(?:Mon|Tue|Wed|Thu|Fri|Sat|Sun)\s+([A-Za-z]{3,})\s+(\d{1,2}),?\s*(\d{4})', text)
    if m:
        month = MONTH_MAP.get(m.group(1).lower()[:3])
        if month:
            day, year = int(m.group(2)), int(m.group(3))
            if _validate_date(month, day, year):
                return _format_date(month, day, year)
    return None


def _extract_apple_valley_waste_date(text: str) -> Optional[str]:
    """Apple Valley Waste - Invoice Date columnar MM/DD/YYYY"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if 'invoice date' in line.lower():
            for j in range(i + 1, min(i + 3, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


def _extract_city_of_sulphur_springs_date(text: str) -> Optional[str]:
    """City of Sulphur Springs - Date columnar M/DD/YYYY"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if line.strip().lower() == 'date':
            for j in range(i + 1, min(i + 3, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


def _extract_pro_disposal_date(text: str) -> Optional[str]:
    """Pro Disposal - Weekday Month DD, YYYY (TrashBilling)"""
    text = _normalize_text(text)
    m = re.search(r'(?:Mon|Tue|Wed|Thu|Fri|Sat|Sun)\s+([A-Za-z]{3,})\s+(\d{1,2}),?\s*(\d{4})', text)
    if m:
        month = MONTH_MAP.get(m.group(1).lower()[:3])
        if month:
            day, year = int(m.group(2)), int(m.group(3))
            if _validate_date(month, day, year):
                return _format_date(month, day, year)
    return None


def _extract_royal_oak_recycling_date(text: str) -> Optional[str]:
    """Royal Oak Recycling - MM/DD/YYYY after invoice number"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if 'no.' in line.lower() and re.search(r'\d{5,}', line):
            for j in range(i + 1, min(i + 3, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


def _extract_the_trash_guys_date(text: str) -> Optional[str]:
    """The Trash Guys - Weekday Month DD, YYYY (TrashBilling)"""
    text = _normalize_text(text)
    m = re.search(r'(?:Mon|Tue|Wed|Thu|Fri|Sat|Sun)\s+([A-Za-z]{3,})\s+(\d{1,2}),?\s*(\d{4})', text)
    if m:
        month = MONTH_MAP.get(m.group(1).lower()[:3])
        if month:
            day, year = int(m.group(2)), int(m.group(3))
            if _validate_date(month, day, year):
                return _format_date(month, day, year)
    return None


def _extract_ameriwaste_date(text: str) -> Optional[str]:
    """Ameriwaste - Date: Weekday Month DD, YYYY (TrashBilling)"""
    text = _normalize_text(text)
    m = re.search(r'Date:\s*(?:Mon|Tue|Wed|Thu|Fri|Sat|Sun)\s+([A-Za-z]{3,})\s+(\d{1,2}),?\s*(\d{4})', text, re.IGNORECASE)
    if m:
        month = MONTH_MAP.get(m.group(1).lower()[:3])
        if month:
            day, year = int(m.group(2)), int(m.group(3))
            if _validate_date(month, day, year):
                return _format_date(month, day, year)
    return None


def _extract_black_earth_compost_date(text: str) -> Optional[str]:
    """Black Earth Compost - DATE columnar (wide spacing)"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if line.strip().upper() == 'DATE':
            for j in range(i + 1, min(i + 10, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


def _extract_hoglands_transfer_date(text: str) -> Optional[str]:
    """Hogland's Transfer - Invoice Date: inline or Freight bill date columnar"""
    text = _normalize_text(text)
    # Try Invoice Date: inline first (most common)
    m = re.search(r'Invoice\s+Date:\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})', text, re.IGNORECASE)
    if m:
        return _parse_date_match(m, 'MDY')
    # Fallback to Freight bill date columnar
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if 'freight bill date' in line.lower():
            for j in range(i + 1, min(i + 3, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


def _extract_bnb_disposal_date(text: str) -> Optional[str]:
    """BNB Disposal - Weekday Month DD, YYYY (TrashBilling)"""
    text = _normalize_text(text)
    m = re.search(r'(?:Mon|Tue|Wed|Thu|Fri|Sat|Sun)\s+([A-Za-z]{3,})\s+(\d{1,2}),?\s*(\d{4})', text)
    if m:
        month = MONTH_MAP.get(m.group(1).lower()[:3])
        if month:
            day, year = int(m.group(2)), int(m.group(3))
            if _validate_date(month, day, year):
                return _format_date(month, day, year)
    return None


def _extract_willey_disposal_date(text: str) -> Optional[str]:
    """Willey Disposal - DATE columnar MM/DD/YYYY"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if line.strip().upper() == 'DATE':
            for j in range(i + 1, min(i + 8, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


def _extract_junk_king_date(text: str) -> Optional[str]:
    """Junk King - Invoice Date columnar Month DD, YYYY"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if 'invoice date' in line.lower():
            for j in range(i + 1, min(i + 5, len(lines))):
                m = re.match(r'^\s*([A-Za-z]{3,})\s+(\d{1,2}),?\s*(\d{4})\s*$', lines[j].strip())
                if m:
                    month = MONTH_MAP.get(m.group(1).lower()[:3])
                    if month:
                        day, year = int(m.group(2)), int(m.group(3))
                        if _validate_date(month, day, year):
                            return _format_date(month, day, year)
    return None


# =============================================================================
# TRANCHE 33 - February 2026
# =============================================================================

def _extract_city_of_hickory_date(text: str) -> Optional[str]:
    """City of Hickory - BILL DATE/CYCLE columnar MM/DD/YY"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if 'bill date' in line.lower():
            # Look backwards for date value (header/value layout)
            for j in range(max(0, i - 10), i):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


def _extract_eco_sanitation_date(text: str) -> Optional[str]:
    """Eco Sanitation - Weekday Month DD, YYYY (TrashBilling)"""
    text = _normalize_text(text)
    m = re.search(r'(?:Mon|Tue|Wed|Thu|Fri|Sat|Sun)\s+([A-Za-z]{3,})\s+(\d{1,2}),?\s*(\d{4})', text)
    if m:
        month = MONTH_MAP.get(m.group(1).lower()[:3])
        if month:
            day, year = int(m.group(2)), int(m.group(3))
            if _validate_date(month, day, year):
                return _format_date(month, day, year)
    return None


def _extract_chambersburg_waste_paper_date(text: str) -> Optional[str]:
    """Chambersburg Waste Paper - Date columnar MM/DD/YYYY"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if line.strip().lower() == 'date':
            for j in range(i + 1, min(i + 5, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


def _extract_miamitown_auto_parts_date(text: str) -> Optional[str]:
    """Miamitown Auto Parts - Statement Date: inline M/D/YYYY"""
    text = _normalize_text(text)
    m = re.search(r'Statement\s+Date:\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})', text, re.IGNORECASE)
    if m:
        return _parse_date_match(m, 'MDY')
    return None


def _extract_countryside_disposal_date(text: str) -> Optional[str]:
    """Countryside Disposal - Weekday Month DD, YYYY (TrashBilling)"""
    text = _normalize_text(text)
    m = re.search(r'(?:Mon|Tue|Wed|Thu|Fri|Sat|Sun)\s+([A-Za-z]{3,})\s+(\d{1,2}),?\s*(\d{4})', text)
    if m:
        month = MONTH_MAP.get(m.group(1).lower()[:3])
        if month:
            day, year = int(m.group(2)), int(m.group(3))
            if _validate_date(month, day, year):
                return _format_date(month, day, year)
    return None


def _extract_iron_city_express_date(text: str) -> Optional[str]:
    """Iron City Express - Invoice Date columnar M/D/YY"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if 'invoice date' in line.lower():
            for j in range(i + 1, min(i + 3, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


def _extract_city_of_great_falls_date(text: str) -> Optional[str]:
    """City of Great Falls - Due Date columnar (use as proxy)"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if 'due date' in line.lower():
            for j in range(i + 1, min(i + 3, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


def _extract_jay_mechams_date(text: str) -> Optional[str]:
    """Jay Mecham's - Date columnar M/D/YYYY"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if line.strip().lower() == 'date':
            for j in range(i + 1, min(i + 5, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


def _extract_mcud_manatee_date(text: str) -> Optional[str]:
    """MCUD Manatee - Service Period MM/DD (extract first date with year inference)"""
    text = _normalize_text(text)
    # Try to find Service Period
    m = re.search(r'Service\s+Period\s+(\d{1,2})[/\-](\d{1,2})', text, re.IGNORECASE)
    if m:
        month, day = int(m.group(1)), int(m.group(2))
        # Infer year from context - look for 4-digit year nearby
        year_match = re.search(r'20\d{2}', text)
        if year_match:
            year = int(year_match.group())
        else:
            year = 2025
        if _validate_date(month, day, year):
            return _format_date(month, day, year)
    return None


def _extract_hughes_trash_removal_date(text: str) -> Optional[str]:
    """Hughes Trash Removal - INVOICE DATE inline MM/DD/YY"""
    text = _normalize_text(text)
    m = re.search(r'INVOICE\s+DATE\s+(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})', text, re.IGNORECASE)
    if m:
        return _parse_date_match(m, 'MDY')
    return None


def _extract_roadrunner_sanitation_date(text: str) -> Optional[str]:
    """Roadrunner Sanitation - Weekday Month DD, YYYY (TrashBilling)"""
    text = _normalize_text(text)
    m = re.search(r'(?:Mon|Tue|Wed|Thu|Fri|Sat|Sun)\s+([A-Za-z]{3,})\s+(\d{1,2}),?\s*(\d{4})', text)
    if m:
        month = MONTH_MAP.get(m.group(1).lower()[:3])
        if month:
            day, year = int(m.group(2)), int(m.group(3))
            if _validate_date(month, day, year):
                return _format_date(month, day, year)
    return None


def _extract_total_disposal_inc_date(text: str) -> Optional[str]:
    """Total Disposal Inc - INVOICE DATE columnar M/DD/YYYY"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if 'invoice date' in line.lower():
            for j in range(i + 1, min(i + 3, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


def _extract_kc_disposal_date(text: str) -> Optional[str]:
    """KC Disposal - Date columnar (look for M/D/YY in early lines)"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if line.strip().lower() == 'date':
            for j in range(i + 1, min(i + 10, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


def _extract_greenway_waste_date(text: str) -> Optional[str]:
    """Greenway Waste - Service Date: inline MM/DD/YYYY"""
    text = _normalize_text(text)
    m = re.search(r'Service\s+Date:\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})', text, re.IGNORECASE)
    if m:
        return _parse_date_match(m, 'MDY')
    return None


def _extract_filco_date(text: str) -> Optional[str]:
    """Filco - Invoice Date: inline MM/DD/YYYY"""
    text = _normalize_text(text)
    m = re.search(r'Invoice\s+Date:\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})', text, re.IGNORECASE)
    if m:
        return _parse_date_match(m, 'MDY')
    return None


# =============================================================================
# TRANCHE 34 - February 2026
# =============================================================================

def _extract_garden_state_waste_management_date(text: str) -> Optional[str]:
    """Garden State Waste Management - Weekday Month DD, YYYY (TrashBilling)"""
    text = _normalize_text(text)
    m = re.search(r'(?:Mon|Tue|Wed|Thu|Fri|Sat|Sun)\s+([A-Za-z]{3,})\s+(\d{1,2}),?\s*(\d{4})', text)
    if m:
        month = MONTH_MAP.get(m.group(1).lower()[:3])
        if month:
            day, year = int(m.group(2)), int(m.group(3))
            if _validate_date(month, day, year):
                return _format_date(month, day, year)
    return None


def _extract_bi_county_disposal_date(text: str) -> Optional[str]:
    """Bi-County Disposal - Invoice Date columnar MM/DD/YYYY"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if 'invoice date' in line.lower():
            for j in range(i + 1, min(i + 8, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


def _extract_golden_environmental_date(text: str) -> Optional[str]:
    """Golden Environmental - Weekday Month DD, YYYY (TrashBilling)"""
    text = _normalize_text(text)
    m = re.search(r'(?:Mon|Tue|Wed|Thu|Fri|Sat|Sun)\s+([A-Za-z]{3,})\s+(\d{1,2}),?\s*(\d{4})', text)
    if m:
        month = MONTH_MAP.get(m.group(1).lower()[:3])
        if month:
            day, year = int(m.group(2)), int(m.group(3))
            if _validate_date(month, day, year):
                return _format_date(month, day, year)
    return None


def _extract_nauset_disposal_date(text: str) -> Optional[str]:
    """Nauset Disposal - STATEMENT DATE columnar M/D/YYYY"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if 'statement date' in line.lower():
            for j in range(i + 1, min(i + 3, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


def _extract_brask_enterprises_date(text: str) -> Optional[str]:
    """Brask Enterprises - DATE columnar M/D/YYYY"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if line.strip().upper() == 'DATE':
            for j in range(i + 1, min(i + 8, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


def _extract_wyoming_waste_services_date(text: str) -> Optional[str]:
    """Wyoming Waste Services - STATEMENT DATE columnar MM/DD/YY"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if 'statement date' in line.lower():
            for j in range(i + 1, min(i + 8, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


def _extract_city_of_st_anthony_date(text: str) -> Optional[str]:
    """City of St Anthony - Service from columnar MM/DD/YY"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if 'service from' in line.lower():
            for j in range(i + 1, min(i + 8, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


def _extract_star_waste_date(text: str) -> Optional[str]:
    """Star Waste - Weekday Month DD YYYY (no comma)"""
    text = _normalize_text(text)
    m = re.search(r'(?:Mon|Tue|Wed|Thu|Fri|Sat|Sun)\s+([A-Za-z]{3,})\s+(\d{1,2})\s+(\d{4})', text)
    if m:
        month = MONTH_MAP.get(m.group(1).lower()[:3])
        if month:
            day, year = int(m.group(2)), int(m.group(3))
            if _validate_date(month, day, year):
                return _format_date(month, day, year)
    return None


def _extract_reworld_date(text: str) -> Optional[str]:
    """Reworld - MM-DD-YYYY manifest date format"""
    text = _normalize_text(text)
    m = re.search(r'(\d{1,2})-(\d{1,2})-(\d{4})', text)
    if m:
        return _parse_date_match(m, 'MDY')
    return None


def _extract_city_of_conyers_date(text: str) -> Optional[str]:
    """City of Conyers - INVOICE DATE columnar MM/DD/YYYY"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if 'invoice date' in line.lower():
            for j in range(i + 1, min(i + 8, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


def _extract_treasure_coast_recycling_date(text: str) -> Optional[str]:
    """Treasure Coast Recycling - Date columnar MM/DD/YYYY"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if line.strip().lower() == 'date':
            for j in range(i + 1, min(i + 5, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


def _extract_north_georgia_waste_date(text: str) -> Optional[str]:
    """North Georgia Waste - Weekday Month DD, YYYY (TrashBilling)"""
    text = _normalize_text(text)
    m = re.search(r'(?:Mon|Tue|Wed|Thu|Fri|Sat|Sun)\s+([A-Za-z]{3,})\s+(\d{1,2}),?\s*(\d{4})', text)
    if m:
        month = MONTH_MAP.get(m.group(1).lower()[:3])
        if month:
            day, year = int(m.group(2)), int(m.group(3))
            if _validate_date(month, day, year):
                return _format_date(month, day, year)
    return None


def _extract_myers_container_service_date(text: str) -> Optional[str]:
    """Myers Container Service - Weekday Month DD, YYYY (TrashBilling)"""
    text = _normalize_text(text)
    m = re.search(r'(?:Mon|Tue|Wed|Thu|Fri|Sat|Sun)\s+([A-Za-z]{3,})\s+(\d{1,2}),?\s*(\d{4})', text)
    if m:
        month = MONTH_MAP.get(m.group(1).lower()[:3])
        if month:
            day, year = int(m.group(2)), int(m.group(3))
            if _validate_date(month, day, year):
                return _format_date(month, day, year)
    return None


def _extract_keys_sanitary_date(text: str) -> Optional[str]:
    """Keys Sanitary - INV DATE columnar MM/DD/YY"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if 'inv date' in line.lower():
            for j in range(i + 1, min(i + 3, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


def _extract_larry_d_marshall_disposal_date(text: str) -> Optional[str]:
    """Larry D Marshall Disposal - Weekday Month DD, YYYY (TrashBilling)"""
    text = _normalize_text(text)
    m = re.search(r'(?:Mon|Tue|Wed|Thu|Fri|Sat|Sun)\s+([A-Za-z]{3,})\s+(\d{1,2}),?\s*(\d{4})', text)
    if m:
        month = MONTH_MAP.get(m.group(1).lower()[:3])
        if month:
            day, year = int(m.group(2)), int(m.group(3))
            if _validate_date(month, day, year):
                return _format_date(month, day, year)
    return None


# =============================================================================
# TRANCHE 35: NEI Pennsylvania, Container Rental Co, Butler Disposal Systems,
#             Golden Triangle Waste, Forever Clean, Glendale Arizona Utilities,
#             Omni, Bridge City Sanitation, City of Mesquite, City of Oakland Park,
#             Talon Sanitation, Marpan Supply
# =============================================================================

def _extract_nei_pennsylvania_date(text: str) -> Optional[str]:
    """NEI Pennsylvania - DATE columnar MM/DD/YYYY"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if line.strip().upper() == 'DATE':
            for j in range(i + 1, min(i + 8, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


def _extract_container_rental_co_date(text: str) -> Optional[str]:
    """Container Rental Co - INV DATE columnar MM/DD/YY"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if 'inv date' in line.lower():
            for j in range(i + 1, min(i + 3, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


def _extract_butler_disposal_systems_date(text: str) -> Optional[str]:
    """Butler Disposal Systems - Weekday Month DD, YYYY (TrashBilling)"""
    text = _normalize_text(text)
    m = re.search(r'(?:Mon|Tue|Wed|Thu|Fri|Sat|Sun)\s+([A-Za-z]{3,})\s+(\d{1,2}),?\s*(\d{4})', text)
    if m:
        month = MONTH_MAP.get(m.group(1).lower()[:3])
        if month:
            day, year = int(m.group(2)), int(m.group(3))
            if _validate_date(month, day, year):
                return _format_date(month, day, year)
    return None


def _extract_golden_triangle_waste_date(text: str) -> Optional[str]:
    """Golden Triangle Waste - DATE columnar MM/DD/YYYY"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if line.strip().upper() == 'DATE':
            for j in range(i + 1, min(i + 5, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


def _extract_forever_clean_date(text: str) -> Optional[str]:
    """Forever Clean - Invoice Date columnar Mon D, YYYY"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if 'invoice date' in line.lower():
            for j in range(i + 1, min(i + 3, len(lines))):
                m = re.match(r'^\s*([A-Za-z]{3,})\s+(\d{1,2}),?\s*(\d{4})\s*$', lines[j].strip())
                if m:
                    month = MONTH_MAP.get(m.group(1).lower()[:3])
                    if month:
                        day, year = int(m.group(2)), int(m.group(3))
                        if _validate_date(month, day, year):
                            return _format_date(month, day, year)
    return None


def _extract_glendale_arizona_utilities_date(text: str) -> Optional[str]:
    """Glendale Arizona Utilities - BILL DATE columnar MM/DD/YYYY"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if 'bill date' in line.lower():
            for j in range(i + 1, min(i + 3, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


def _extract_omni_date(text: str) -> Optional[str]:
    """Omni - DATE: MM/DD/YY inline"""
    text = _normalize_text(text)
    m = re.search(r'DATE:\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})', text, re.IGNORECASE)
    if m:
        return _parse_date_match(m, 'MDY')
    return None


def _extract_bridge_city_sanitation_date(text: str) -> Optional[str]:
    """Bridge City Sanitation - DATE columnar M/DD/YYYY"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if line.strip().upper() == 'DATE':
            for j in range(i + 1, min(i + 3, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


def _extract_city_of_mesquite_date(text: str) -> Optional[str]:
    """City of Mesquite - Invoice Date REVERSE columnar M/DD/YY (value BEFORE label)"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if 'invoice date' in line.lower():
            # Date value appears BEFORE the label line
            for j in range(max(0, i - 3), i):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


def _extract_city_of_oakland_park_date(text: str) -> Optional[str]:
    """City of Oakland Park - Bill Date columnar MM/DD/YYYY"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if 'bill date' in line.lower():
            for j in range(i + 1, min(i + 3, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


def _extract_talon_sanitation_date(text: str) -> Optional[str]:
    """Talon Sanitation - Invoice date: columnar MM/DD/YYYY"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if 'invoice date' in line.lower():
            for j in range(i + 1, min(i + 6, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


def _extract_marpan_supply_date(text: str) -> Optional[str]:
    """Marpan Supply - DATE columnar MM/DD/YY"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if line.strip().upper() == 'DATE':
            for j in range(i + 1, min(i + 6, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


# =============================================================================
# TRANCHE 36: Cedar Grove, Hotchkiss Disposal, Sunshine Disposal & Recycling,
#             Dugger Trash Service, Waste Resources Gardena, Walters Sanitary Service,
#             Woodward's Disposal, Al Clawson Disposal, Mt Diablo Resource Recovery,
#             Blue Ridge Waste, Alpha Waste Disposal, Texas Commercial Waste
# =============================================================================

def _extract_cedar_grove_date(text: str) -> Optional[str]:
    """Cedar Grove - Invoice Date columnar MM/DD/YYYY"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if 'invoice date' in line.lower():
            for j in range(i + 1, min(i + 3, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


def _extract_hotchkiss_disposal_date(text: str) -> Optional[str]:
    """Hotchkiss Disposal - Weekday Month DD, YYYY (TrashBilling)"""
    text = _normalize_text(text)
    m = re.search(r'(?:Mon|Tue|Wed|Thu|Fri|Sat|Sun)\s+([A-Za-z]{3,})\s+(\d{1,2}),?\s*(\d{4})', text)
    if m:
        month = MONTH_MAP.get(m.group(1).lower()[:3])
        if month:
            day, year = int(m.group(2)), int(m.group(3))
            if _validate_date(month, day, year):
                return _format_date(month, day, year)
    return None


def _extract_sunshine_disposal_recycling_date(text: str) -> Optional[str]:
    """Sunshine Disposal & Recycling - BILLING DATE columnar M/DD/YY"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if 'billing date' in line.lower():
            for j in range(i + 1, min(i + 5, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


def _extract_dugger_trash_service_date(text: str) -> Optional[str]:
    """Dugger Trash Service - Invoice date: columnar MM/DD/YYYY"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if 'invoice date' in line.lower():
            for j in range(i + 1, min(i + 6, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


def _extract_waste_resources_gardena_date(text: str) -> Optional[str]:
    """Waste Resources Gardena - INVOICE DATE columnar M/DD/YYYY"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if 'invoice date' in line.lower():
            for j in range(i + 1, min(i + 6, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


def _extract_walters_sanitary_service_date(text: str) -> Optional[str]:
    """Walters Sanitary Service - INV DATE columnar MM/DD/YY"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if 'inv date' in line.lower():
            for j in range(i + 1, min(i + 3, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


def _extract_woodwards_disposal_date(text: str) -> Optional[str]:
    """Woodward's Disposal - Invoice Date: columnar MM/DD/YYYY"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if 'invoice date' in line.lower():
            for j in range(i + 1, min(i + 3, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


def _extract_al_clawson_disposal_date(text: str) -> Optional[str]:
    """Al Clawson Disposal - Invoice Date columnar M/DD/YY"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if 'invoice date' in line.lower():
            for j in range(i + 1, min(i + 3, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


def _extract_mt_diablo_resource_recovery_date(text: str) -> Optional[str]:
    """Mt Diablo Resource Recovery - Invoice Date: MM/DD/YYYY inline"""
    text = _normalize_text(text)
    m = re.search(r'Invoice\s+Date:\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})', text, re.IGNORECASE)
    if m:
        return _parse_date_match(m, 'MDY')
    return None


def _extract_blue_ridge_waste_date(text: str) -> Optional[str]:
    """Blue Ridge Waste - Invoice Date columnar DD Mon, YYYY"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if 'invoice date' in line.lower():
            for j in range(i + 1, min(i + 3, len(lines))):
                m = re.match(r'^\s*(\d{1,2})\s+([A-Za-z]{3,}),?\s*(\d{4})\s*$', lines[j].strip())
                if m:
                    day = int(m.group(1))
                    month = MONTH_MAP.get(m.group(2).lower()[:3])
                    year = int(m.group(3))
                    if month and _validate_date(month, day, year):
                        return _format_date(month, day, year)
    return None


def _extract_alpha_waste_disposal_date(text: str) -> Optional[str]:
    """Alpha Waste Disposal - Invoice Date: Mon DD, YYYY inline"""
    text = _normalize_text(text)
    m = re.search(r'Invoice\s+Date:\s*([A-Za-z]{3,})\s+(\d{1,2}),?\s*(\d{4})', text, re.IGNORECASE)
    if m:
        month = MONTH_MAP.get(m.group(1).lower()[:3])
        if month:
            day, year = int(m.group(2)), int(m.group(3))
            if _validate_date(month, day, year):
                return _format_date(month, day, year)
    return None


def _extract_texas_commercial_waste_date(text: str) -> Optional[str]:
    """Texas Commercial Waste - Invoice Date: MM/DD/YYYY inline"""
    text = _normalize_text(text)
    m = re.search(r'Invoice\s+Date:\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})', text, re.IGNORECASE)
    if m:
        return _parse_date_match(m, 'MDY')
    return None


# =============================================================================
# TRANCHE 37: Good's Disposal, Charlie's Waste, Madison Materials,
#             LaVeine Sanitation, T & G Sanitation, Roadrunner Rubbish,
#             Marck Recycling and Waste, Elite Recycling, Denali Disposal,
#             Bloom Waste, Patterson Sanitation, 4G Futures
# =============================================================================

def _extract_goods_disposal_date(text: str) -> Optional[str]:
    """Good's Disposal - DATE columnar MM/DD/YYYY"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if line.strip().upper() == 'DATE':
            for j in range(i + 1, min(i + 8, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


def _extract_charlies_waste_date(text: str) -> Optional[str]:
    """Charlie's Waste - Mon-DD-YY format (Aug-01-25)"""
    text = _normalize_text(text)
    m = re.search(r'([A-Za-z]{3})-(\d{2})-(\d{2,4})', text)
    if m:
        month = MONTH_MAP.get(m.group(1).lower()[:3])
        if month:
            day = int(m.group(2))
            year = int(m.group(3))
            if year < 100:
                year += 2000
            if _validate_date(month, day, year):
                return _format_date(month, day, year)
    return None


def _extract_madison_materials_date(text: str) -> Optional[str]:
    """Madison Materials - INV DATE columnar MM/DD/YY"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if 'inv date' in line.lower():
            for j in range(i + 1, min(i + 3, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


def _extract_laveine_sanitation_date(text: str) -> Optional[str]:
    """LaVeine Sanitation - Invoice/Date headers then value MM/DD/YYYY"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if line.strip().lower() == 'invoice':
            # Check if next line is "Date"
            if i + 1 < len(lines) and lines[i + 1].strip().lower() == 'date':
                # Date value should follow
                for j in range(i + 2, min(i + 5, len(lines))):
                    m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                    if m:
                        return _parse_date_match(m, 'MDY')
    return None


def _extract_t_g_sanitation_date(text: str) -> Optional[str]:
    """T & G Sanitation - Weekday Month DD, YYYY (TrashBilling)"""
    text = _normalize_text(text)
    m = re.search(r'(?:Mon|Tue|Wed|Thu|Fri|Sat|Sun)\s+([A-Za-z]{3,})\s+(\d{1,2}),?\s*(\d{4})', text)
    if m:
        month = MONTH_MAP.get(m.group(1).lower()[:3])
        if month:
            day, year = int(m.group(2)), int(m.group(3))
            if _validate_date(month, day, year):
                return _format_date(month, day, year)
    return None


def _extract_roadrunner_rubbish_date(text: str) -> Optional[str]:
    """Roadrunner Rubbish - INV DATE columnar MM/DD/YY"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if 'inv date' in line.lower():
            for j in range(i + 1, min(i + 3, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


def _extract_marck_recycling_and_waste_date(text: str) -> Optional[str]:
    """Marck Recycling and Waste - Date columnar Mon-DD-YY (Jul-01-25)"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if line.strip().lower() == 'date':
            for j in range(i + 1, min(i + 5, len(lines))):
                m = re.match(r'^\s*([A-Za-z]{3})-(\d{2})-(\d{2,4})\s*$', lines[j].strip())
                if m:
                    month = MONTH_MAP.get(m.group(1).lower()[:3])
                    if month:
                        day = int(m.group(2))
                        year = int(m.group(3))
                        if year < 100:
                            year += 2000
                        if _validate_date(month, day, year):
                            return _format_date(month, day, year)
    return None


def _extract_elite_recycling_date(text: str) -> Optional[str]:
    """Elite Recycling - Mon D, YYYY at top of invoice"""
    text = _normalize_text(text)
    # Look for Mon D, YYYY format in first 10 lines
    lines = text.split('\n')[:10]
    for line in lines:
        m = re.match(r'^\s*([A-Za-z]{3,})\s+(\d{1,2}),?\s*(\d{4})\s*$', line.strip())
        if m:
            month = MONTH_MAP.get(m.group(1).lower()[:3])
            if month:
                day, year = int(m.group(2)), int(m.group(3))
                if _validate_date(month, day, year):
                    return _format_date(month, day, year)
    return None


def _extract_denali_disposal_date(text: str) -> Optional[str]:
    """Denali Disposal - Invoice Date: MM/DD/YYYY inline"""
    text = _normalize_text(text)
    m = re.search(r'Invoice\s+Date:\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})', text, re.IGNORECASE)
    if m:
        return _parse_date_match(m, 'MDY')
    return None


def _extract_bloom_waste_date(text: str) -> Optional[str]:
    """Bloom Waste - INV DATE columnar MM/DD/YY"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if 'inv date' in line.lower():
            for j in range(i + 1, min(i + 3, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


def _extract_patterson_sanitation_date(text: str) -> Optional[str]:
    """Patterson Sanitation - BILLING DATE columnar MM/DD/YY"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if 'billing date' in line.lower():
            for j in range(i + 1, min(i + 3, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    # Also check same line after label
    m = re.search(r'BILLING\s+DATE\s+(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})', text, re.IGNORECASE)
    if m:
        return _parse_date_match(m, 'MDY')
    return None


def _extract_4g_futures_date(text: str) -> Optional[str]:
    """4G Futures - Date columnar M/DD/YYYY"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if line.strip().lower() == 'date':
            for j in range(i + 1, min(i + 5, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


# =============================================================================
# TRANCHE 38 (February 2026)
# =============================================================================

def _extract_iv_waste_date(text: str) -> Optional[str]:
    """IV Waste - INVOICE DATE columnar MM/DD/YYYY"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if 'INVOICE DATE' in line.upper():
            for j in range(i + 1, min(i + 5, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


def _extract_k_k_sanitation_date(text: str) -> Optional[str]:
    """K & K Sanitation - Invoice date: columnar MM/DD/YYYY"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if 'invoice date' in line.lower():
            for j in range(i + 1, min(i + 6, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


def _extract_waste_harmonics_date(text: str) -> Optional[str]:
    """Waste Harmonics - DATE columnar MM/DD/YYYY"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if line.strip().upper() == 'DATE':
            for j in range(i + 1, min(i + 8, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


def _extract_bozeman_mt_utilities_date(text: str) -> Optional[str]:
    """Bozeman MT Utilities - BILLING DATE: inline MM/DD/YYYY"""
    text = _normalize_text(text)
    m = re.search(r'BILLING\s+DATE:\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})', text, re.IGNORECASE)
    if m:
        return _parse_date_match(m, 'MDY')
    return None


def _extract_taylor_sons_date(text: str) -> Optional[str]:
    """Taylor & Sons - DATE columnar MM/DD/YYYY"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if line.strip().upper() == 'DATE':
            for j in range(i + 1, min(i + 8, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


def _extract_united_rentals_date(text: str) -> Optional[str]:
    """United Rentals - STATEMENT DATE columnar MM/DD/YY"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if 'STATEMENT DATE' in line.upper():
            for j in range(i + 1, min(i + 5, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


def _extract_nevada_recycling_date(text: str) -> Optional[str]:
    """Nevada Recycling - Payment date columnar MM/DD/YYYY"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if 'payment date' in line.lower():
            for j in range(i + 1, min(i + 6, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


def _extract_tygarts_valley_sanitation_date(text: str) -> Optional[str]:
    """Tygarts Valley Sanitation - received on MM/DD/YYYY inline"""
    text = _normalize_text(text)
    m = re.search(r'received\s+on\s+(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})', text, re.IGNORECASE)
    if m:
        return _parse_date_match(m, 'MDY')
    return None


def _extract_miedema_sanitation_date(text: str) -> Optional[str]:
    """Miedema Sanitation - Date columnar M/D/YYYY"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if line.strip().lower() == 'date':
            for j in range(i + 1, min(i + 5, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


def _extract_quincy_recycling_date(text: str) -> Optional[str]:
    """Quincy Recycling - Recv Date: inline MM/DD/YYYY"""
    text = _normalize_text(text)
    m = re.search(r'Recv\s+Date:\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})', text, re.IGNORECASE)
    if m:
        return _parse_date_match(m, 'MDY')
    return None


def _extract_smurfit_date(text: str) -> Optional[str]:
    """Smurfit - Date: columnar M/DD/YYYY"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if line.strip().lower() == 'date:':
            for j in range(i + 1, min(i + 5, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


def _extract_escondido_disposal_date(text: str) -> Optional[str]:
    """Escondido Disposal - Billing Date columnar MM/DD/YY"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if 'billing date' in line.lower():
            for j in range(i + 1, min(i + 8, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


# =============================================================================
# TRANCHE 39
# =============================================================================

def _extract_express_disposal_date(text: str) -> Optional[str]:
    """Express Disposal - STATEMENT columnar MM/DD/YYYY"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if line.strip().upper() == 'STATEMENT':
            for j in range(i + 1, min(i + 5, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


def _extract_waste_services_manchester_date(text: str) -> Optional[str]:
    """Waste Services Manchester - INV DATE columnar MM/DD/YY"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if 'INV DATE' in line.upper():
            for j in range(i + 1, min(i + 5, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


def _extract_avas_waste_removal_date(text: str) -> Optional[str]:
    """Ava's Waste Removal - TrashBilling 'received on' format"""
    m = re.search(r'received on (\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})', text, re.IGNORECASE)
    if m:
        return _parse_date_match(m, 'MDY')
    # Fallback: TrashBilling Weekday Mon DD, YYYY
    m = re.search(r'(?:Mon|Tue|Wed|Thu|Fri|Sat|Sun)\s+([A-Za-z]{3})\s+(\d{1,2}),?\s*(\d{4})', text)
    if m:
        month = MONTH_MAP.get(m.group(1).lower())
        if month:
            day, year = int(m.group(2)), int(m.group(3))
            if _validate_date(month, day, year):
                return _format_date(month, day, year)
    return None


def _extract_bki_recycling_date(text: str) -> Optional[str]:
    """BKI Recycling - DD Mon YYYY inline format after invoice number"""
    text = _normalize_text(text)
    # Pattern: 18 Nov 2025
    m = re.search(r'(\d{1,2})\s+([A-Za-z]{3})\s+(\d{4})', text)
    if m:
        day = int(m.group(1))
        month = MONTH_MAP.get(m.group(2).lower())
        year = int(m.group(3))
        if month and _validate_date(month, day, year):
            return _format_date(month, day, year)
    return None


def _extract_valley_sanitation_llc_date(text: str) -> Optional[str]:
    """Valley Sanitation LLC - TrashBilling 'received on' format"""
    m = re.search(r'received on (\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})', text, re.IGNORECASE)
    if m:
        return _parse_date_match(m, 'MDY')
    # Fallback: TrashBilling Weekday Mon DD, YYYY
    m = re.search(r'(?:Mon|Tue|Wed|Thu|Fri|Sat|Sun)\s+([A-Za-z]{3})\s+(\d{1,2}),?\s*(\d{4})', text)
    if m:
        month = MONTH_MAP.get(m.group(1).lower())
        if month:
            day, year = int(m.group(2)), int(m.group(3))
            if _validate_date(month, day, year):
                return _format_date(month, day, year)
    return None


def _extract_ridgerunner_container_date(text: str) -> Optional[str]:
    """Ridgerunner Container - DATE columnar MM/DD/YY"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if line.strip().upper() == 'DATE':
            for j in range(i + 1, min(i + 8, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


def _extract_recycling_services_of_florida_date(text: str) -> Optional[str]:
    """Recycling Services of Florida - DATE columnar Mon-DD-YY format"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if line.strip().upper() == 'DATE':
            for j in range(i + 1, min(i + 10, len(lines))):
                # Mon-DD-YY format (Dec-31-25)
                m = re.match(r'^\s*([A-Za-z]{3})-(\d{1,2})-(\d{2,4})\s*$', lines[j].strip())
                if m:
                    month = MONTH_MAP.get(m.group(1).lower())
                    if month:
                        day, year = int(m.group(2)), int(m.group(3))
                        if year < 100:
                            year = 2000 + year if year < 50 else 1900 + year
                        if _validate_date(month, day, year):
                            return _format_date(month, day, year)
    return None


def _extract_rick_taylor_date(text: str) -> Optional[str]:
    """Rick Taylor - DATE: inline Month DD, YYYY format"""
    text = _normalize_text(text)
    # Pattern: DATE:\nDecember 31, 2025
    m = re.search(r'DATE:\s*\n?\s*([A-Za-z]+)\s+(\d{1,2}),?\s*(\d{4})', text, re.IGNORECASE)
    if m:
        month = MONTH_MAP.get(m.group(1).lower()[:3])
        if month:
            day, year = int(m.group(2)), int(m.group(3))
            if _validate_date(month, day, year):
                return _format_date(month, day, year)
    return None


def _extract_klumm_brothers_date(text: str) -> Optional[str]:
    """Klumm Brothers - TrashBilling Weekday Mon DD, YYYY format"""
    text = _normalize_text(text)
    # Pattern: Tue Apr 29, 2025
    m = re.search(r'(?:Mon|Tue|Wed|Thu|Fri|Sat|Sun)\s+([A-Za-z]{3})\s+(\d{1,2}),?\s*(\d{4})', text)
    if m:
        month = MONTH_MAP.get(m.group(1).lower())
        if month:
            day, year = int(m.group(2)), int(m.group(3))
            if _validate_date(month, day, year):
                return _format_date(month, day, year)
    return None


def _extract_green_guy_recycling_date(text: str) -> Optional[str]:
    """Green Guy Recycling - Invoice date: inline MM/DD/YYYY"""
    text = _normalize_text(text)
    m = re.search(r'Invoice\s+date:\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})', text, re.IGNORECASE)
    if m:
        return _parse_date_match(m, 'MDY')
    return None


def _extract_mars_city_of_beatrice_date(text: str) -> Optional[str]:
    """MARS City of Beatrice - STATEMENT Date columnar MM/DD/YYYY"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if 'STATEMENT' in line.upper():
            for j in range(i + 1, min(i + 8, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


def _extract_midwest_disposal_il_date(text: str) -> Optional[str]:
    """Midwest Disposal IL - Invoice date: columnar MM/DD/YYYY"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if 'invoice date' in line.lower():
            for j in range(i + 1, min(i + 8, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


# =============================================================================
# TRANCHE 40
# =============================================================================

def _extract_lake_disposal_service_date(text: str) -> Optional[str]:
    """Lake Disposal Service - DATE columnar M/D/YYYY"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if line.strip().upper() == 'DATE':
            for j in range(i + 1, min(i + 5, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


def _extract_tropical_trash_date(text: str) -> Optional[str]:
    """Tropical Trash - DATE columnar Mon D, YYYY (NavuSoft)"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if line.strip().upper() == 'DATE':
            for j in range(i + 1, min(i + 8, len(lines))):
                m = re.match(r'^\s*([A-Za-z]{3})\s+(\d{1,2}),?\s*(\d{4})\s*$', lines[j].strip())
                if m:
                    month = MONTH_MAP.get(m.group(1).lower())
                    if month:
                        day, year = int(m.group(2)), int(m.group(3))
                        if _validate_date(month, day, year):
                            return _format_date(month, day, year)
    return None


def _extract_troupe_waste_date(text: str) -> Optional[str]:
    """Troupe Waste - Date columnar Mon-DD-YY"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if line.strip().lower() == 'date':
            for j in range(i + 1, min(i + 10, len(lines))):
                m = re.match(r'^\s*([A-Za-z]{3})-(\d{1,2})-(\d{2,4})\s*$', lines[j].strip())
                if m:
                    month = MONTH_MAP.get(m.group(1).lower())
                    if month:
                        day, year = int(m.group(2)), int(m.group(3))
                        if year < 100:
                            year = 2000 + year if year < 50 else 1900 + year
                        if _validate_date(month, day, year):
                            return _format_date(month, day, year)
    return None


def _extract_aw_iron_metal_date(text: str) -> Optional[str]:
    """A&W Iron Metal - Invoice Date: inline MM/DD/YYYY"""
    text = _normalize_text(text)
    m = re.search(r'Invoice\s+Date:\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})', text, re.IGNORECASE)
    if m:
        return _parse_date_match(m, 'MDY')
    return None


def _extract_chesapeake_waste_date(text: str) -> Optional[str]:
    """Chesapeake Waste - MM/DD/YYYY before Statement Date (reverse columnar)"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if 'statement date' in line.lower():
            for j in range(max(0, i - 5), i):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


def _extract_expert_transportation_date(text: str) -> Optional[str]:
    """Expert Transportation - Date columnar M/D/YYYY"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if line.strip().lower() == 'date':
            for j in range(i + 1, min(i + 8, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


def _extract_seadrunar_recycling_date(text: str) -> Optional[str]:
    """Seadrunar Recycling - BILLING DATE columnar M/DD/YY"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if 'BILLING DATE' in line.upper():
            for j in range(i + 1, min(i + 10, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


def _extract_greenbrier_valley_solid_waste_date(text: str) -> Optional[str]:
    """Greenbrier Valley Solid Waste - TrashBilling Weekday Mon DD, YYYY"""
    text = _normalize_text(text)
    m = re.search(r'(?:Mon|Tue|Wed|Thu|Fri|Sat|Sun)\s+([A-Za-z]{3})\s+(\d{1,2}),?\s*(\d{4})', text)
    if m:
        month = MONTH_MAP.get(m.group(1).lower())
        if month:
            day, year = int(m.group(2)), int(m.group(3))
            if _validate_date(month, day, year):
                return _format_date(month, day, year)
    return None


def _extract_bts_inc_date(text: str) -> Optional[str]:
    """BTS Inc - Date columnar M/D/YYYY"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if line.strip().lower() == 'date':
            for j in range(i + 1, min(i + 8, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


def _extract_town_country_disposal_date(text: str) -> Optional[str]:
    """Town & Country Disposal - STATEMENT DATE columnar MM/DD/YY (Waste Connections style)"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if 'STATEMENT DATE' in line.upper():
            for j in range(i + 1, min(i + 8, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


def _extract_haul_away_waste_date(text: str) -> Optional[str]:
    """Haul Away Waste - INVOICE DATE with date on line before (reverse columnar)"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if 'INVOICE DATE' in line.upper():
            for j in range(max(0, i - 3), i):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


def _extract_napa_recycling_date(text: str) -> Optional[str]:
    """Napa Recycling - STATEMENT DATE: inline MM/DD/YYYY"""
    text = _normalize_text(text)
    m = re.search(r'STATEMENT\s+DATE:\s*\n?\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})', text, re.IGNORECASE)
    if m:
        return _parse_date_match(m, 'MDY')
    return None


# =============================================================================
# TRANCHE 41
# =============================================================================

def _extract_city_of_lakeland_fl_date(text: str) -> Optional[str]:
    """City of Lakeland FL - Billing Date: inline MM/DD/YYYY"""
    text = _normalize_text(text)
    m = re.search(r'Billing\s+Date:\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})', text, re.IGNORECASE)
    if m:
        return _parse_date_match(m, 'MDY')
    return None


def _extract_wm_compactor_solutions_date(text: str) -> Optional[str]:
    """WM Compactor Solutions - Invoice Date: columnar M/D/YYYY"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if 'invoice date' in line.lower():
            for j in range(i + 1, min(i + 5, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


def _extract_mills_brothers_date(text: str) -> Optional[str]:
    """Mills Brothers - INVOICE DATE: MM-DD-YY inline"""
    text = _normalize_text(text)
    m = re.search(r'INVOICE\s+DATE:\s*(\d{1,2})-(\d{1,2})-(\d{2,4})', text, re.IGNORECASE)
    if m:
        return _parse_date_match(m, 'MDY')
    return None


def _extract_arrowhead_waste_date(text: str) -> Optional[str]:
    """Arrowhead Waste - Invoice Date: inline MM/DD/YYYY"""
    text = _normalize_text(text)
    m = re.search(r'Invoice\s+Date:\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})', text, re.IGNORECASE)
    if m:
        return _parse_date_match(m, 'MDY')
    return None


def _extract_waterman_recycling_date(text: str) -> Optional[str]:
    """Waterman Recycling - TrashBilling 'received on' format"""
    m = re.search(r'received on (\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})', text, re.IGNORECASE)
    if m:
        return _parse_date_match(m, 'MDY')
    return None


def _extract_ramona_disposal_date(text: str) -> Optional[str]:
    """Ramona Disposal - Billing Date columnar MM/DD/YY"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if 'billing date' in line.lower():
            for j in range(i + 1, min(i + 8, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


def _extract_redwood_waste_date(text: str) -> Optional[str]:
    """Redwood Waste - STATEMENT DATE columnar MM/DD/YY (Waste Connections style)"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if 'STATEMENT DATE' in line.upper():
            for j in range(i + 1, min(i + 8, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


def _extract_tri_state_disposal_date(text: str) -> Optional[str]:
    """Tri-State Disposal - Invoice Date columnar MM/DD/YYYY"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if 'invoice date' in line.lower():
            for j in range(i + 1, min(i + 8, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


def _extract_enevo_date(text: str) -> Optional[str]:
    """Enevo - DATE columnar MM/DD/YYYY"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if line.strip().upper() == 'DATE':
            for j in range(i + 1, min(i + 5, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


def _extract_jd_parker_date(text: str) -> Optional[str]:
    """JD Parker - Invoice Date: columnar MM/DD/YYYY"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if 'invoice date' in line.lower():
            for j in range(i + 1, min(i + 10, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


def _extract_aj_waste_systems_date(text: str) -> Optional[str]:
    """AJ Waste Systems - Invoice Date columnar M/D/YY (date appears before label)"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if 'invoice date' in line.lower():
            # Check lines before the label (reverse columnar)
            for j in range(max(0, i - 5), i):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


def _extract_darob_date(text: str) -> Optional[str]:
    """Darob - Date columnar M/D/YYYY"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if line.strip().lower() == 'date':
            for j in range(i + 1, min(i + 8, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


# =============================================================================
# TRANCHE 42
# =============================================================================

def _extract_weavers_sanitation_date(text: str) -> Optional[str]:
    """Weaver's Sanitation - INVOICE DATE columnar M/D/YYYY"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if 'INVOICE DATE' in line.upper():
            for j in range(i + 1, min(i + 5, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


def _extract_akat_scrap_metal_date(text: str) -> Optional[str]:
    """Akat Scrap Metal - Date before Date label (reverse columnar)"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if line.strip().lower() == 'date':
            for j in range(max(0, i - 5), i):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


def _extract_city_of_bakersfield_date(text: str) -> Optional[str]:
    """City of Bakersfield - Invoice Date inline MM/DD/YYYY"""
    text = _normalize_text(text)
    m = re.search(r'Invoice\s+Date\s+(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})', text, re.IGNORECASE)
    if m:
        return _parse_date_match(m, 'MDY')
    return None


def _extract_city_of_visalia_date(text: str) -> Optional[str]:
    """City of Visalia - FROM MM/DD/YYYY To date range"""
    text = _normalize_text(text)
    m = re.search(r'FROM\s+(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s+To', text, re.IGNORECASE)
    if m:
        return _parse_date_match(m, 'MDY')
    return None


def _extract_shank_waste_date(text: str) -> Optional[str]:
    """Shank Waste - Invoice Date: inline MM/DD/YYYY"""
    text = _normalize_text(text)
    m = re.search(r'Invoice\s+Date:\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})', text, re.IGNORECASE)
    if m:
        return _parse_date_match(m, 'MDY')
    return None


def _extract_steves_sanitation_date(text: str) -> Optional[str]:
    """Steve's Sanitation - TrashBilling 'received on' format"""
    m = re.search(r'received on (\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})', text, re.IGNORECASE)
    if m:
        return _parse_date_match(m, 'MDY')
    return None


def _extract_lemhi_sanitation_date(text: str) -> Optional[str]:
    """Lemhi Sanitation - Date columnar M/D/YYYY"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if line.strip().lower() == 'date':
            for j in range(i + 1, min(i + 5, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


def _extract_weidle_sanitation_date(text: str) -> Optional[str]:
    """Weidle Sanitation - DATE columnar MM/DD/YYYY"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if line.strip().upper() == 'DATE':
            for j in range(i + 1, min(i + 8, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


def _extract_choice_waste_services_date(text: str) -> Optional[str]:
    """Choice Waste Services - DATE columnar Mon DD, YYYY (NavuSoft)"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if line.strip().upper() == 'DATE':
            for j in range(i + 1, min(i + 5, len(lines))):
                m = re.match(r'^\s*([A-Za-z]{3})\s+(\d{1,2}),?\s*(\d{4})\s*$', lines[j].strip())
                if m:
                    month = MONTH_MAP.get(m.group(1).lower())
                    if month:
                        day, year = int(m.group(2)), int(m.group(3))
                        if _validate_date(month, day, year):
                            return _format_date(month, day, year)
    return None


def _extract_hale_county_public_works_date(text: str) -> Optional[str]:
    """Hale County Public Works - SERVICE DATE columnar MM/DD/YYYY"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if 'SERVICE DATE' in line.upper():
            for j in range(i + 1, min(i + 5, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


def _extract_pike_county_solid_waste_date(text: str) -> Optional[str]:
    """Pike County Solid Waste - TrashBilling 'received on' format"""
    m = re.search(r'received on (\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})', text, re.IGNORECASE)
    if m:
        return _parse_date_match(m, 'MDY')
    return None


def _extract_pm_reis_trucking_date(text: str) -> Optional[str]:
    """P&M Reis Trucking - Invoice Date inline MM/DD/YYYY"""
    text = _normalize_text(text)
    m = re.search(r'Invoice\s+Date\s+(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})', text, re.IGNORECASE)
    if m:
        return _parse_date_match(m, 'MDY')
    return None


# =============================================================================
# TRANCHE 43
# =============================================================================

def _extract_full_circle_recycling_date(text: str) -> Optional[str]:
    """Full Circle Recycling - Invoice Date columnar MM/DD/YY"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if 'invoice date' in line.lower():
            for j in range(i + 1, min(i + 5, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


def _extract_kohlmorgan_hauling_date(text: str) -> Optional[str]:
    """Kohlmorgan Hauling - DATE inline MM/DD/YYYY"""
    text = _normalize_text(text)
    m = re.search(r'\bDATE\s+(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})', text)
    if m:
        return _parse_date_match(m, 'MDY')
    return None


def _extract_econo_waste_date(text: str) -> Optional[str]:
    """Econo Waste - Statement Date columnar MM/DD/YYYY"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if 'statement date' in line.lower():
            for j in range(i + 1, min(i + 5, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


def _extract_raekar_date(text: str) -> Optional[str]:
    """RaeKar - TrashBilling 'received on' format"""
    m = re.search(r'received on (\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})', text, re.IGNORECASE)
    if m:
        return _parse_date_match(m, 'MDY')
    return None


def _extract_action_trucking_date(text: str) -> Optional[str]:
    """Action Trucking - Invoice Date DD Mon, YYYY"""
    text = _normalize_text(text)
    m = re.search(r'Invoice\s*\n?\s*(?:D|d)?ate\s*\n?\s*(\d{1,2})\s+([A-Za-z]{3}),?\s*(\d{4})', text)
    if m:
        day = int(m.group(1))
        month = MONTH_MAP.get(m.group(2).lower())
        year = int(m.group(3))
        if month and _validate_date(month, day, year):
            return _format_date(month, day, year)
    return None


def _extract_whites_sanitation_date(text: str) -> Optional[str]:
    """Whites Sanitation - INV DATE columnar MM/DD/YY"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if 'INV DATE' in line.upper():
            for j in range(i + 1, min(i + 5, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


def _extract_lance_refuse_date(text: str) -> Optional[str]:
    """Lance Refuse - DATE inline MM/DD/YYYY"""
    text = _normalize_text(text)
    m = re.search(r'\bDATE\s+(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})', text)
    if m:
        return _parse_date_match(m, 'MDY')
    return None


def _extract_lift_waste_date(text: str) -> Optional[str]:
    """Lift Waste - DATE columnar MM/DD/YYYY"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if line.strip().upper() == 'DATE':
            for j in range(i + 1, min(i + 8, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


def _extract_long_beach_container_date(text: str) -> Optional[str]:
    """Long Beach Container - Date columnar M/D/YYYY"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if line.strip().lower() == 'date':
            for j in range(i + 1, min(i + 10, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


def _extract_pullman_disposal_date(text: str) -> Optional[str]:
    """Pullman Disposal - INVOICE DATE columnar MM/DD/YYYY"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if 'INVOICE DATE' in line.upper():
            for j in range(i + 1, min(i + 5, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


def _extract_ez_disposal_date(text: str) -> Optional[str]:
    """EZ Disposal - DATE columnar Mon DD, YYYY (NavuSoft)"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if line.strip().upper() == 'DATE':
            for j in range(i + 1, min(i + 8, len(lines))):
                m = re.match(r'^\s*([A-Za-z]{3})\s+(\d{1,2}),?\s*(\d{4})\s*$', lines[j].strip())
                if m:
                    month = MONTH_MAP.get(m.group(1).lower())
                    if month:
                        day, year = int(m.group(2)), int(m.group(3))
                        if _validate_date(month, day, year):
                            return _format_date(month, day, year)
    return None


def _extract_control_waste_date(text: str) -> Optional[str]:
    """Control Waste - Date: columnar MM/DD/YY"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if line.strip().lower() == 'date:':
            for j in range(i + 1, min(i + 5, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


# =============================================================================
# TRANCHE 44
# =============================================================================

def _extract_nva_services_date(text: str) -> Optional[str]:
    """NVA Services - Invoice Date MM/DD/YYYY inline"""
    text = _normalize_text(text)
    m = re.search(r'Invoice\s+Date\s+(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})', text, re.IGNORECASE)
    if m:
        return _parse_date_match(m, 'MDY')
    return None


def _extract_tahoe_basin_container_date(text: str) -> Optional[str]:
    """Tahoe Basin Container - Date columnar MM/DD/YYYY"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if line.strip().lower() == 'date':
            for j in range(i + 1, min(i + 8, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


def _extract_aws_date(text: str) -> Optional[str]:
    """AWS - Invoice Date: inline MM/DD/YYYY"""
    text = _normalize_text(text)
    m = re.search(r'Invoice\s+Date:\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})', text, re.IGNORECASE)
    if m:
        return _parse_date_match(m, 'MDY')
    return None


def _extract_boston_baler_date(text: str) -> Optional[str]:
    """Boston Baler - Invoice date columnar M-D-YYYY"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if 'invoice date' in line.lower():
            for j in range(i + 1, min(i + 5, len(lines))):
                m = re.match(r'^\s*(\d{1,2})-(\d{1,2})-(\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


def _extract_city_of_foley_date(text: str) -> Optional[str]:
    """City of Foley - DATE: inline M/D/YYYY"""
    text = _normalize_text(text)
    m = re.search(r'\bDATE:\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})', text)
    if m:
        return _parse_date_match(m, 'MDY')
    return None


def _extract_city_of_richardson_date(text: str) -> Optional[str]:
    """City of Richardson - Billing Date: inline MM/DD/YYYY"""
    text = _normalize_text(text)
    m = re.search(r'Billing\s+Date:\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})', text, re.IGNORECASE)
    if m:
        return _parse_date_match(m, 'MDY')
    return None


def _extract_city_of_sallisaw_date(text: str) -> Optional[str]:
    """City of Sallisaw - Billing Period End columnar MM/DD/YYYY"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if 'billing period end' in line.lower():
            for j in range(i + 1, min(i + 5, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


def _extract_lincoln_county_solid_waste_date(text: str) -> Optional[str]:
    """Lincoln County Solid Waste - Date columnar MM/DD/YYYY"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if line.strip().lower() == 'date':
            for j in range(i + 1, min(i + 5, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


def _extract_norris_sanitation_date(text: str) -> Optional[str]:
    """Norris Sanitation - TrashBilling 'received on' format"""
    m = re.search(r'received on (\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})', text, re.IGNORECASE)
    if m:
        return _parse_date_match(m, 'MDY')
    return None


def _extract_kamps_pallets_date(text: str) -> Optional[str]:
    """Kamps Pallets - Invoice Date columnar M/D/YYYY"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if 'invoice date' in line.lower():
            for j in range(i + 1, min(i + 5, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


def _extract_crane_roll_off_date(text: str) -> Optional[str]:
    """Crane Roll-Off - Statement Date columnar MM/DD/YYYY"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if 'statement date' in line.lower():
            for j in range(i + 1, min(i + 5, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


def _extract_heartland_waste_management_date(text: str) -> Optional[str]:
    """Heartland Waste Management - Date columnar M/D/YYYY"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if line.strip().lower() == 'date':
            for j in range(i + 1, min(i + 5, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


# --- Tranche 45 ---

def _extract_city_of_tulare_date(text: str) -> Optional[str]:
    """City of Tulare - Billing Date: columnar MM/DD/YYYY"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if 'billing date' in line.lower():
            for j in range(i + 1, min(i + 5, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


def _extract_rhino_waste_date(text: str) -> Optional[str]:
    """Rhino Waste - Date: Mon DD, YYYY inline"""
    text = _normalize_text(text)
    m = re.search(r'Date:\s*([A-Za-z]{3})\s+(\d{1,2}),?\s*(\d{4})', text, re.IGNORECASE)
    if m:
        month = MONTH_MAP.get(m.group(1).lower()[:3])
        if month:
            day, year = int(m.group(2)), int(m.group(3))
            if _validate_date(month, day, year):
                return _format_date(month, day, year)
    return None


def _extract_miller_enterprises_date(text: str) -> Optional[str]:
    """Miller Enterprises - Weekday Mon DD, YYYY inline (TrashBilling)"""
    text = _normalize_text(text)
    m = re.search(r'(?:Mon|Tue|Wed|Thu|Fri|Sat|Sun)\s+([A-Za-z]{3})\s+(\d{1,2}),?\s*(\d{4})', text, re.IGNORECASE)
    if m:
        month = MONTH_MAP.get(m.group(1).lower()[:3])
        if month:
            day, year = int(m.group(2)), int(m.group(3))
            if _validate_date(month, day, year):
                return _format_date(month, day, year)
    return None


def _extract_city_of_mesa_date(text: str) -> Optional[str]:
    """City of Mesa - Bill Date: MM/DD/YY inline"""
    text = _normalize_text(text)
    m = re.search(r'Bill\s+Date:\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})', text, re.IGNORECASE)
    if m:
        return _parse_date_match(m, 'MDY')
    return None


def _extract_cowboy_sanitation_date(text: str) -> Optional[str]:
    """Cowboy Sanitation - TrashBilling 'received on' format"""
    text = _normalize_text(text)
    m = re.search(r'received on (\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})', text, re.IGNORECASE)
    if m:
        return _parse_date_match(m, 'MDY')
    return None


def _extract_cwrr_date(text: str) -> Optional[str]:
    """CWRR - SERVICE PERIOD start date M/D/YY"""
    text = _normalize_text(text)
    m = re.search(r'SERVICE\s+PERIOD\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})', text, re.IGNORECASE)
    if m:
        return _parse_date_match(m, 'MDY')
    return None


def _extract_city_of_fayette_date(text: str) -> Optional[str]:
    """City of Fayette - SERVICE TO columnar MM/DD/YY"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if 'service to' in line.lower():
            for j in range(i + 1, min(i + 3, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


def _extract_premier_disposal_date(text: str) -> Optional[str]:
    """Premier Disposal - Invoice Date wide columnar MM/DD/YYYY"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if 'invoice date' in line.lower():
            for j in range(i + 1, min(i + 10, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


def _extract_nowrush_recycling_date(text: str) -> Optional[str]:
    """Nowrush Recycling - DATE wide columnar MM/DD/YYYY"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if line.strip().upper() == 'DATE':
            for j in range(i + 1, min(i + 10, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


def _extract_seaside_waste_date(text: str) -> Optional[str]:
    """Seaside Waste - Invoice Date: MM/DD/YYYY inline"""
    text = _normalize_text(text)
    m = re.search(r'Invoice\s+Date:\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})', text, re.IGNORECASE)
    if m:
        return _parse_date_match(m, 'MDY')
    return None


def _extract_city_of_temple_tx_date(text: str) -> Optional[str]:
    """City of Temple TX - Bill Date columnar MM/DD/YYYY"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if 'bill date' in line.lower():
            for j in range(i + 1, min(i + 5, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


def _extract_marin_sanitary_date(text: str) -> Optional[str]:
    """Marin Sanitary - Billing Period columnar MM/DD/YYYY"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if 'billing period' in line.lower():
            for j in range(i + 1, min(i + 5, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


# --- Tranche 46 ---

def _extract_city_sanitary_service_date(text: str) -> Optional[str]:
    """City Sanitary Service - Bill Date wide columnar Month DD, YYYY"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if 'bill date' in line.lower():
            for j in range(i + 1, min(i + 10, len(lines))):
                m = re.match(r'^\s*([A-Za-z]+)\s+(\d{1,2}),?\s*(\d{4})\s*$', lines[j].strip())
                if m:
                    month = MONTH_MAP.get(m.group(1).lower()[:3])
                    if month:
                        day, year = int(m.group(2)), int(m.group(3))
                        if _validate_date(month, day, year):
                            return _format_date(month, day, year)
    return None


def _extract_byre_brothers_date(text: str) -> Optional[str]:
    """Byre Brothers - TrashBilling 'received on' format"""
    text = _normalize_text(text)
    m = re.search(r'received on (\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})', text, re.IGNORECASE)
    if m:
        return _parse_date_match(m, 'MDY')
    return None


def _extract_sanitation_services_date(text: str) -> Optional[str]:
    """Sanitation Services - INVOICE DATE: wide columnar MM/DD/YYYY"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if 'invoice date' in line.lower():
            for j in range(i + 1, min(i + 10, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


def _extract_cook_maintenance_date(text: str) -> Optional[str]:
    """Cook Maintenance - Current Date line wide columnar M/D/YYYY"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if 'current d' in line.lower() or line.strip().lower() == 'date':
            for j in range(i + 1, min(i + 5, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


def _extract_florida_waste_solutions_date(text: str) -> Optional[str]:
    """Florida Waste Solutions - Invoice Date columnar M/D/YY"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if 'invoice date' in line.lower():
            for j in range(i + 1, min(i + 5, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


def _extract_empire_recycling_corporation_date(text: str) -> Optional[str]:
    """Empire Recycling Corporation - Recv Date: MM/DD/YYYY inline"""
    text = _normalize_text(text)
    m = re.search(r'Recv\s+Date:\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})', text, re.IGNORECASE)
    if m:
        return _parse_date_match(m, 'MDY')
    return None


def _extract_bl_disposal_date(text: str) -> Optional[str]:
    """B&L Disposal - Invoice Date columnar MM/DD/YYYY"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if 'invoice date' in line.lower():
            for j in range(i + 1, min(i + 5, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


def _extract_hem_service_company_date(text: str) -> Optional[str]:
    """HEM Service Company - Date wide columnar M/D/YYYY"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if line.strip().lower() == 'date':
            for j in range(i + 1, min(i + 5, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


def _extract_shred360_date(text: str) -> Optional[str]:
    """Shred360 - DATE MM/DD/YYYY inline"""
    text = _normalize_text(text)
    m = re.search(r'\bDATE\s+(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})', text)
    if m:
        return _parse_date_match(m, 'MDY')
    return None


def _extract_william_sullivan_date(text: str) -> Optional[str]:
    """William Sullivan - Date wide columnar M/D/YYYY"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if line.strip().lower() == 'date':
            for j in range(i + 1, min(i + 5, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


def _extract_mr_e_date(text: str) -> Optional[str]:
    """MR & E - Bill Date: M/D/YY inline"""
    text = _normalize_text(text)
    m = re.search(r'Bill\s+Date:\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})', text, re.IGNORECASE)
    if m:
        return _parse_date_match(m, 'MDY')
    return None


def _extract_local_waste_solution_date(text: str) -> Optional[str]:
    """Local Waste Solution - Invoice date: MM/DD/YYYY inline"""
    text = _normalize_text(text)
    m = re.search(r'Invoice\s+date:\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})', text, re.IGNORECASE)
    if m:
        return _parse_date_match(m, 'MDY')
    return None


# --- Tranche 47 ---

def _extract_paso_robles_waste_date(text: str) -> Optional[str]:
    """Paso Robles Waste - Invoice Date wide columnar M/D/YY"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if 'invoice date' in line.lower():
            for j in range(i + 1, min(i + 10, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


def _extract_coos_bay_sanitary_date(text: str) -> Optional[str]:
    """Coos Bay Sanitary - STATEMENT DATE wide columnar MM/DD/YYYY"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if 'statement date' in line.lower():
            for j in range(i + 1, min(i + 10, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


def _extract_porter_trash_date(text: str) -> Optional[str]:
    """Porter Trash - DATE wide columnar MM/DD/YYYY"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if line.strip().upper() == 'DATE':
            for j in range(i + 1, min(i + 5, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


def _extract_abs_sanitation_date(text: str) -> Optional[str]:
    """ABS Sanitation - TrashBilling Weekday Mon DD, YYYY"""
    text = _normalize_text(text)
    m = re.search(r'(?:Mon|Tue|Wed|Thu|Fri|Sat|Sun)\s+([A-Za-z]{3})\s+(\d{1,2}),?\s*(\d{4})', text, re.IGNORECASE)
    if m:
        month = MONTH_MAP.get(m.group(1).lower()[:3])
        if month:
            day, year = int(m.group(2)), int(m.group(3))
            if _validate_date(month, day, year):
                return _format_date(month, day, year)
    return None


def _extract_tennis_sanitation_date(text: str) -> Optional[str]:
    """Tennis Sanitation - Billing Date MM/DD/YYYY inline"""
    text = _normalize_text(text)
    m = re.search(r'Billing\s+Date\s+(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})', text, re.IGNORECASE)
    if m:
        return _parse_date_match(m, 'MDY')
    return None


def _extract_rubatino_refuse_date(text: str) -> Optional[str]:
    """Rubatino Refuse - SERVICE DATE columnar with date range"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if 'service date' in line.lower():
            for j in range(i + 1, min(i + 10, len(lines))):
                # Match date range like "08/01/2025-08/31/2025" and take first date
                m = re.match(r'^\s*\d?(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


def _extract_waterman_recy_disposal_date(text: str) -> Optional[str]:
    """Waterman Recy & Disposal - Bill Date: M/D/YY inline"""
    text = _normalize_text(text)
    m = re.search(r'Bill\s+Date:\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})', text, re.IGNORECASE)
    if m:
        return _parse_date_match(m, 'MDY')
    return None


def _extract_h_town_hauling_date(text: str) -> Optional[str]:
    """H-Town Hauling - Due date columnar M/D/YY"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if line.strip().lower() == 'due':
            for j in range(i + 1, min(i + 3, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


def _extract_deep_south_sanitation_date(text: str) -> Optional[str]:
    """Deep South Sanitation - TrashBilling 'received on' format"""
    text = _normalize_text(text)
    m = re.search(r'received on (\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})', text, re.IGNORECASE)
    if m:
        return _parse_date_match(m, 'MDY')
    return None


def _extract_hepaco_date(text: str) -> Optional[str]:
    """Hepaco - Invoice No line then search for date"""
    text = _normalize_text(text)
    m = re.search(r'Invoice\s+No\s+\d+.*?(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})', text, re.IGNORECASE | re.DOTALL)
    if m:
        return _parse_date_match(m, 'MDY')
    # Fallback: look for Last Service Date
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if 'last service date' in line.lower():
            for j in range(i + 1, min(i + 5, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


def _extract_fayette_waste_date(text: str) -> Optional[str]:
    """Fayette Waste - INV DATE columnar MM/DD/YY"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if 'inv date' in line.lower():
            for j in range(i + 1, min(i + 5, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


def _extract_pacific_disposal_date(text: str) -> Optional[str]:
    """Pacific Disposal - STATEMENT DATE wide columnar MM/DD/YY"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if 'statement date' in line.lower():
            for j in range(i + 1, min(i + 10, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


# --- Tranche 48 ---

def _extract_waste_control_date(text: str) -> Optional[str]:
    """Waste Control - INVOICE DATE: wide columnar MM/DD/YYYY"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if 'invoice date' in line.lower():
            for j in range(i + 1, min(i + 10, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


def _extract_t_mac_inc_date(text: str) -> Optional[str]:
    """T-Mac Inc - TrashBilling 'received on' format"""
    text = _normalize_text(text)
    m = re.search(r'received on (\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})', text, re.IGNORECASE)
    if m:
        return _parse_date_match(m, 'MDY')
    return None


def _extract_swinger_sanitation_date(text: str) -> Optional[str]:
    """Swinger Sanitation - Invoice Date: columnar M/D/YYYY"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if 'invoice date' in line.lower():
            for j in range(i + 1, min(i + 5, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


def _extract_barbarino_disposal_date(text: str) -> Optional[str]:
    """Barbarino Disposal - Bill Date: columnar M/D/YYYY"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if 'bill date' in line.lower():
            for j in range(i + 1, min(i + 5, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


def _extract_bavarian_waste_date(text: str) -> Optional[str]:
    """Bavarian Waste - INVOICE DATE: columnar MM/DD/YYYY"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if 'invoice date' in line.lower():
            for j in range(i + 1, min(i + 5, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


def _extract_city_of_ketchikan_date(text: str) -> Optional[str]:
    """City of Ketchikan - Date of Bill columnar MM/DD/YYYY"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if 'date of bill' in line.lower():
            for j in range(i + 1, min(i + 5, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


def _extract_oregon_city_garbage_date(text: str) -> Optional[str]:
    """Oregon City Garbage - INVOICE DATE wide columnar MM/DD/YY"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if 'invoice date' in line.lower():
            for j in range(i + 1, min(i + 10, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


def _extract_maverick_waste_date(text: str) -> Optional[str]:
    """Maverick Waste - TrashBilling Weekday Mon DD, YYYY"""
    text = _normalize_text(text)
    m = re.search(r'(?:Mon|Tue|Wed|Thu|Fri|Sat|Sun)\s+([A-Za-z]{3})\s+(\d{1,2}),?\s*(\d{4})', text, re.IGNORECASE)
    if m:
        month = MONTH_MAP.get(m.group(1).lower()[:3])
        if month:
            day, year = int(m.group(2)), int(m.group(3))
            if _validate_date(month, day, year):
                return _format_date(month, day, year)
    return None


def _extract_gardner_disposal_service_date(text: str) -> Optional[str]:
    """Gardner Disposal Service - NOTICE DATE: columnar MM/DD/YYYY"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if 'notice date' in line.lower():
            for j in range(i + 1, min(i + 5, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


def _extract_gresham_sanitary_service_date(text: str) -> Optional[str]:
    """Gresham Sanitary Service - Bill Date columnar MM/DD/YYYY"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if 'bill date' in line.lower():
            for j in range(i + 1, min(i + 5, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


def _extract_douglas_disposal_date(text: str) -> Optional[str]:
    """Douglas Disposal - Statement Date wide columnar MM/DD/YYYY"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if 'statement date' in line.lower():
            for j in range(i + 1, min(i + 10, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


def _extract_a1_porta_potty_date(text: str) -> Optional[str]:
    """A1 Porta Potty - Date columnar Mon DD, YYYY"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if line.strip().lower() == 'date':
            for j in range(i + 1, min(i + 5, len(lines))):
                m = re.match(r'^\s*([A-Za-z]{3})\s+(\d{1,2}),?\s*(\d{4})\s*$', lines[j].strip())
                if m:
                    month = MONTH_MAP.get(m.group(1).lower()[:3])
                    if month:
                        day, year = int(m.group(2)), int(m.group(3))
                        if _validate_date(month, day, year):
                            return _format_date(month, day, year)
    return None


# --- Tranche 49 ---

def _extract_modern_disposal_date(text: str) -> Optional[str]:
    """Modern Disposal - Service Date: MM/DD/YYYY inline"""
    text = _normalize_text(text)
    m = re.search(r'Service\s+Date:\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})', text, re.IGNORECASE)
    if m:
        return _parse_date_match(m, 'MDY')
    return None


def _extract_bower_disposal_date(text: str) -> Optional[str]:
    """Bower Disposal - Weekday Mon DD, YYYY inline"""
    text = _normalize_text(text)
    m = re.search(r'(?:Mon|Tue|Wed|Thu|Fri|Sat|Sun)\s+([A-Za-z]{3})\s+(\d{1,2}),?\s*(\d{4})', text, re.IGNORECASE)
    if m:
        month = MONTH_MAP.get(m.group(1).lower()[:3])
        if month:
            day, year = int(m.group(2)), int(m.group(3))
            if _validate_date(month, day, year):
                return _format_date(month, day, year)
    return None


def _extract_arg_services_date(text: str) -> Optional[str]:
    """Arg Services - DATE MM/DD/YYYY inline"""
    text = _normalize_text(text)
    m = re.search(r'\bDATE\s+(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})', text)
    if m:
        return _parse_date_match(m, 'MDY')
    return None


def _extract_sound_disposal_inc_date(text: str) -> Optional[str]:
    """Sound Disposal Inc - Date: columnar MM/DD/YYYY"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if line.strip().lower() == 'date:':
            for j in range(i + 1, min(i + 5, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


def _extract_area_refuse_date(text: str) -> Optional[str]:
    """Area Refuse - INVOICE DATE columnar MM/DD/YYYY"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if 'invoice date' in line.lower():
            for j in range(i + 1, min(i + 5, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


def _extract_bozzuto_brs_services_date(text: str) -> Optional[str]:
    """Bozzuto BRS Services - Invoice Date wide columnar M/D/YY"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if 'invoice date' in line.lower():
            for j in range(i + 1, min(i + 10, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


def _extract_city_of_winters_date(text: str) -> Optional[str]:
    """City of Winters - Invoice Date: reverse columnar MM/DD/YYYY"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if 'invoice date' in line.lower():
            # Date is BEFORE the label
            for j in range(max(0, i - 5), i):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


def _extract_rs_waste_date(text: str) -> Optional[str]:
    """R&S Waste - Invoice Date: MM/DD/YYYY inline"""
    text = _normalize_text(text)
    m = re.search(r'Invoice\s+Date:\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})', text, re.IGNORECASE)
    if m:
        return _parse_date_match(m, 'MDY')
    return None


def _extract_wb_waste_solutions_date(text: str) -> Optional[str]:
    """WB Waste Solutions - INVOICE DATE columnar M/D/YYYY"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if 'invoice date' in line.lower():
            for j in range(i + 1, min(i + 5, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


def _extract_all_state_waste_inc_date(text: str) -> Optional[str]:
    """All State Waste Inc - DATE wide columnar Mon DD, YYYY"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if line.strip().upper() == 'DATE':
            for j in range(i + 1, min(i + 10, len(lines))):
                m = re.match(r'^\s*([A-Za-z]{3})\s+(\d{1,2}),?\s*(\d{4})\s*$', lines[j].strip())
                if m:
                    month = MONTH_MAP.get(m.group(1).lower()[:3])
                    if month:
                        day, year = int(m.group(2)), int(m.group(3))
                        if _validate_date(month, day, year):
                            return _format_date(month, day, year)
    return None


def _extract_perdue_environmental_date(text: str) -> Optional[str]:
    """Perdue Environmental - Invoice Date: wide columnar M/D/YY"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if 'invoice date' in line.lower():
            for j in range(i + 1, min(i + 10, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


def _extract_sanitation_one_date(text: str) -> Optional[str]:
    """Sanitation One - DATE wide columnar MM/DD/YYYY"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if line.strip().upper() == 'DATE':
            for j in range(i + 1, min(i + 10, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


# --- Tranche 50 ---

def _extract_buds_clean_up_service_date(text: str) -> Optional[str]:
    """Bud's Clean Up Service - Invoice date: wide columnar MM/DD/YYYY"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if 'invoice date' in line.lower():
            for j in range(i + 1, min(i + 10, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


def _extract_east_central_kansas_date(text: str) -> Optional[str]:
    """East Central Kansas - Date: Weekday Mon DD, YYYY inline"""
    text = _normalize_text(text)
    m = re.search(r'Date:\s*(?:Mon|Tue|Wed|Thu|Fri|Sat|Sun)\s+([A-Za-z]{3})\s+(\d{1,2}),?\s*(\d{4})', text, re.IGNORECASE)
    if m:
        month = MONTH_MAP.get(m.group(1).lower()[:3])
        if month:
            day, year = int(m.group(2)), int(m.group(3))
            if _validate_date(month, day, year):
                return _format_date(month, day, year)
    return None


def _extract_wisneski_westmoreland_date(text: str) -> Optional[str]:
    """Wisneski Westmoreland - TrashBilling Weekday Mon DD, YYYY"""
    text = _normalize_text(text)
    m = re.search(r'(?:Mon|Tue|Wed|Thu|Fri|Sat|Sun)\s+([A-Za-z]{3})\s+(\d{1,2}),?\s*(\d{4})', text, re.IGNORECASE)
    if m:
        month = MONTH_MAP.get(m.group(1).lower()[:3])
        if month:
            day, year = int(m.group(2)), int(m.group(3))
            if _validate_date(month, day, year):
                return _format_date(month, day, year)
    return None


def _extract_the_shred_truck_date(text: str) -> Optional[str]:
    """The Shred Truck - Date: columnar MM/DD/YYYY"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if line.strip().lower() == 'date:':
            for j in range(i + 1, min(i + 5, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


def _extract_ideal_trash_and_recycling_date(text: str) -> Optional[str]:
    """Ideal Trash and Recycling - Invoice date: wide columnar MM/DD/YYYY"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if 'invoice date' in line.lower():
            for j in range(i + 1, min(i + 10, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


def _extract_syracuse_haulers_date(text: str) -> Optional[str]:
    """Syracuse Haulers - Date wide columnar MM/DD/YYYY"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if line.strip().lower() == 'date':
            for j in range(i + 1, min(i + 5, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


def _extract_coastal_environmental_service_date(text: str) -> Optional[str]:
    """Coastal Environmental Service - INVOICE DATE wide columnar MM/DD/YYYY"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if 'invoice date' in line.lower():
            for j in range(i + 1, min(i + 10, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


def _extract_washler_garbage_date(text: str) -> Optional[str]:
    """Washler Garbage - INVOICE DATE NavuSoft columnar Mon DD, YYYY"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if 'invoice date' in line.lower():
            for j in range(i + 1, min(i + 10, len(lines))):
                m = re.match(r'^\s*([A-Za-z]{3,9})\s+(\d{1,2}),?\s*(\d{4})\s*$', lines[j].strip())
                if m:
                    month = MONTH_MAP.get(m.group(1).lower()[:3])
                    if month:
                        day, year = int(m.group(2)), int(m.group(3))
                        if _validate_date(month, day, year):
                            return _format_date(month, day, year)
    return None


def _extract_city_of_casper_date(text: str) -> Optional[str]:
    """City of Casper - Issued MM/DD/YYYY inline"""
    text = _normalize_text(text)
    m = re.search(r'Issued\s+(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})', text, re.IGNORECASE)
    if m:
        return _parse_date_match(m, 'MDY')
    return None


def _extract_city_of_boynton_beach_date(text: str) -> Optional[str]:
    """City of Boynton Beach - Bill Date: columnar MM/DD/YYYY"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if 'bill date' in line.lower():
            for j in range(i + 1, min(i + 5, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


def _extract_veolia_date(text: str) -> Optional[str]:
    """Veolia - Invoice Date: wide columnar M/D/YY"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if 'invoice date' in line.lower():
            for j in range(i + 1, min(i + 10, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


def _extract_madras_sanitary_service_date(text: str) -> Optional[str]:
    """Madras Sanitary Service - TrashBilling 'received on' format"""
    text = _normalize_text(text)
    m = re.search(r'received on (\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})', text, re.IGNORECASE)
    if m:
        return _parse_date_match(m, 'MDY')
    return None


# --- Tranche 51 ---

def _extract_miles_city_sanitation_date(text: str) -> Optional[str]:
    """Miles City Sanitation - INV DATE columnar MM/DD/YY"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if 'inv date' in line.lower():
            for j in range(i + 1, min(i + 5, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


def _extract_mazza_recycling_date(text: str) -> Optional[str]:
    """Mazza Recycling - INVOICE DATE columnar M/D/YYYY"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if 'invoice date' in line.lower():
            for j in range(i + 1, min(i + 5, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


def _extract_going_green_recycle_date(text: str) -> Optional[str]:
    """Going Green Recycle - Date columnar M/D/YYYY"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if line.strip().lower() == 'date':
            for j in range(i + 1, min(i + 5, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


def _extract_city_of_mcdonough_date(text: str) -> Optional[str]:
    """City of McDonough - Due Date columnar MM/DD/YYYY"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if 'due date' in line.lower():
            for j in range(i + 1, min(i + 5, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


def _extract_greenwaste_date(text: str) -> Optional[str]:
    """GreenWaste - STATEMENT DATE: columnar MM/DD/YYYY"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if 'statement date' in line.lower():
            for j in range(i + 1, min(i + 5, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


def _extract_trinity_disposal_date(text: str) -> Optional[str]:
    """Trinity Disposal - TrashBilling 'received on' format"""
    text = _normalize_text(text)
    m = re.search(r'received on (\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})', text, re.IGNORECASE)
    if m:
        return _parse_date_match(m, 'MDY')
    return None


def _extract_document_destruction_of_virginia_date(text: str) -> Optional[str]:
    """Document Destruction of Virginia - Services through M/D/YYYY inline"""
    text = _normalize_text(text)
    m = re.search(r'Services through (\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})', text, re.IGNORECASE)
    if m:
        return _parse_date_match(m, 'MDY')
    return None


def _extract_sutton_disposal_date(text: str) -> Optional[str]:
    """Sutton Disposal - TrashBilling 'received on' format"""
    text = _normalize_text(text)
    m = re.search(r'received on (\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})', text, re.IGNORECASE)
    if m:
        return _parse_date_match(m, 'MDY')
    return None


def _extract_waste_advantage_date(text: str) -> Optional[str]:
    """Waste Advantage - Invoice Date: inline MM/DD/YYYY"""
    text = _normalize_text(text)
    m = re.search(r'Invoice Date:\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})', text, re.IGNORECASE)
    if m:
        return _parse_date_match(m, 'MDY')
    return None


def _extract_city_of_snellville_date(text: str) -> Optional[str]:
    """City of Snellville - Due Date columnar M/D/YYYY"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if 'due date' in line.lower():
            for j in range(i + 1, min(i + 5, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


def _extract_thompsons_sanitary_service_date(text: str) -> Optional[str]:
    """Thompson's Sanitary Service - Bill Date columnar M/D/YYYY"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if 'bill date' in line.lower():
            for j in range(i + 1, min(i + 5, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


def _extract_city_of_mont_belvieu_date(text: str) -> Optional[str]:
    """City of Mont Belvieu - DATE: inline M/D/YYYY"""
    text = _normalize_text(text)
    m = re.search(r'\bDATE:\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})', text, re.IGNORECASE)
    if m:
        return _parse_date_match(m, 'MDY')
    return None


# --- Tranche 52 ---

def _extract_american_sanitation_date(text: str) -> Optional[str]:
    """American Sanitation - Invoice Date columnar Mon DD, YYYY"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if 'invoice date' in line.lower():
            for j in range(i + 1, min(i + 5, len(lines))):
                m = re.match(r'^\s*([A-Za-z]{3})\s+(\d{1,2}),?\s*(\d{4})\s*$', lines[j].strip())
                if m:
                    month = MONTH_MAP.get(m.group(1).lower()[:3])
                    if month:
                        day, year = int(m.group(2)), int(m.group(3))
                        if _validate_date(month, day, year):
                            return _format_date(month, day, year)
    return None


def _extract_solid_rock_waste_date(text: str) -> Optional[str]:
    """Solid Rock Waste - TrashBilling 'received on' format"""
    text = _normalize_text(text)
    m = re.search(r'received on (\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})', text, re.IGNORECASE)
    if m:
        return _parse_date_match(m, 'MDY')
    return None


def _extract_happy_can_disposal_date(text: str) -> Optional[str]:
    """Happy Can Disposal - Issued Date: columnar Mon DD, YYYY"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if 'issued date' in line.lower():
            for j in range(i + 1, min(i + 5, len(lines))):
                m = re.match(r'^\s*([A-Za-z]{3,9})\s+(\d{1,2}),?\s*(\d{4})\s*$', lines[j].strip())
                if m:
                    month = MONTH_MAP.get(m.group(1).lower()[:3])
                    if month:
                        day, year = int(m.group(2)), int(m.group(3))
                        if _validate_date(month, day, year):
                            return _format_date(month, day, year)
    return None


def _extract_cloquet_sanitary_date(text: str) -> Optional[str]:
    """Cloquet Sanitary - Look for DATE header then find MM/DD/YYYY in transaction"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if line.strip().upper() == 'DATE':
            for j in range(i + 1, min(i + 15, len(lines))):
                m = re.search(r'(\d{1,2})[/\-](\d{1,2})[/\-](\d{4})', lines[j])
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


def _extract_miami_waste_paper_date(text: str) -> Optional[str]:
    """Miami Waste Paper - Date columnar M/D/YYYY"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if line.strip().lower() == 'date':
            for j in range(i + 1, min(i + 5, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


def _extract_city_of_tracy_date(text: str) -> Optional[str]:
    """City of Tracy - Bill Date inline with account MM/DD/YYYY"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if 'bill date' in line.lower():
            for j in range(i + 1, min(i + 5, len(lines))):
                m = re.search(r'(\d{1,2})[/\-](\d{1,2})[/\-](\d{4})', lines[j])
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


def _extract_city_of_mount_vernon_wa_date(text: str) -> Optional[str]:
    """City of Mount Vernon WA - BILL DATE wide columnar MM/DD/YYYY"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if 'bill date' in line.lower():
            for j in range(i + 1, min(i + 5, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


def _extract_rightaway_rolloff_date(text: str) -> Optional[str]:
    """RightAway RollOff - Date columnar M/D/YYYY"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if line.strip().lower() == 'date':
            for j in range(i + 1, min(i + 5, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


def _extract_city_of_windcrest_date(text: str) -> Optional[str]:
    """City of Windcrest - Bill Date wide columnar MM/DD/YYYY"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if 'bill date' in line.lower():
            for j in range(i + 1, min(i + 15, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


def _extract_bgl_suburban_garbage_date(text: str) -> Optional[str]:
    """BGL Suburban Garbage - STATEMENT DATE columnar MM/DD/YYYY"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if 'statement date' in line.lower():
            for j in range(i + 1, min(i + 5, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


def _extract_real_waste_solutions_date(text: str) -> Optional[str]:
    """Real Waste Solutions - DD Mon YYYY inline at top"""
    text = _normalize_text(text)
    m = re.search(r'(\d{1,2})\s+([A-Za-z]{3})\s+(\d{4})', text)
    if m:
        month = MONTH_MAP.get(m.group(2).lower()[:3])
        if month:
            day, year = int(m.group(1)), int(m.group(3))
            if _validate_date(month, day, year):
                return _format_date(month, day, year)
    return None


def _extract_two_men_and_a_junk_truck_date(text: str) -> Optional[str]:
    """Two Men and a Junk Truck - Service Date columnar MM/DD/YYYY"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if 'service date' in line.lower():
            for j in range(i + 1, min(i + 5, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


# --- Tranche 53 ---

def _extract_moler_sanitation_date(text: str) -> Optional[str]:
    """Moler Sanitation - TrashBilling Weekday Mon DD, YYYY inline"""
    text = _normalize_text(text)
    m = re.search(r'(?:Mon|Tue|Wed|Thu|Fri|Sat|Sun)\s+([A-Za-z]{3})\s+(\d{1,2}),?\s*(\d{4})', text, re.IGNORECASE)
    if m:
        month = MONTH_MAP.get(m.group(1).lower()[:3])
        if month:
            day, year = int(m.group(2)), int(m.group(3))
            if _validate_date(month, day, year):
                return _format_date(month, day, year)
    return None


def _extract_lakeland_disposal_wi_date(text: str) -> Optional[str]:
    """Lakeland Disposal WI - Date columnar Month DD YYYY"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if line.strip().lower() == 'date':
            for j in range(i + 1, min(i + 10, len(lines))):
                m = re.match(r'^\s*([A-Za-z]+)\s+(\d{1,2})\s+(\d{4})\s*$', lines[j].strip())
                if m:
                    month = MONTH_MAP.get(m.group(1).lower()[:3])
                    if month:
                        day, year = int(m.group(2)), int(m.group(3))
                        if _validate_date(month, day, year):
                            return _format_date(month, day, year)
    return None


def _extract_shawnee_county_solid_waste_date(text: str) -> Optional[str]:
    """Shawnee County Solid Waste - DUE DATE wide columnar Mon DD, YYYY"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if 'due date' in line.lower():
            for j in range(i + 1, min(i + 5, len(lines))):
                m = re.match(r'^\s*([A-Za-z]{3})\s+(\d{1,2}),?\s*(\d{4})\s*$', lines[j].strip())
                if m:
                    month = MONTH_MAP.get(m.group(1).lower()[:3])
                    if month:
                        day, year = int(m.group(2)), int(m.group(3))
                        if _validate_date(month, day, year):
                            return _format_date(month, day, year)
    return None


def _extract_brandon_industrial_parts_date(text: str) -> Optional[str]:
    """Brandon Industrial Parts - Invoice Date inline DD MMM YY"""
    text = _normalize_text(text)
    m = re.search(r'Invoice Date[_\s]*(\d{1,2})\s+([A-Za-z]{3})\s+(\d{2,4})', text, re.IGNORECASE)
    if m:
        month = MONTH_MAP.get(m.group(2).lower()[:3])
        if month:
            day, year = int(m.group(1)), int(m.group(3))
            if year < 100:
                year += 2000
            if _validate_date(month, day, year):
                return _format_date(month, day, year)
    return None


def _extract_cumberland_services_date(text: str) -> Optional[str]:
    """Cumberland Services - DATE columnar Mon DD, YYYY"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if line.strip().upper() == 'DATE':
            for j in range(i + 1, min(i + 5, len(lines))):
                m = re.match(r'^\s*([A-Za-z]{3})\s+(\d{1,2}),?\s*(\d{4})\s*$', lines[j].strip())
                if m:
                    month = MONTH_MAP.get(m.group(1).lower()[:3])
                    if month:
                        day, year = int(m.group(2)), int(m.group(3))
                        if _validate_date(month, day, year):
                            return _format_date(month, day, year)
    return None


def _extract_hartels_date(text: str) -> Optional[str]:
    """Hartel's - Invoice Date columnar MM/DD/YYYY"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if 'invoice date' in line.lower():
            for j in range(i + 1, min(i + 5, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


def _extract_aaa_trash_service_date(text: str) -> Optional[str]:
    """AAA Trash Service - DATE wide columnar MM/DD/YYYY"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if line.strip().upper() == 'DATE':
            for j in range(i + 1, min(i + 10, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


def _extract_potties_for_the_rockies_date(text: str) -> Optional[str]:
    """Potties for the Rockies - Date columnar M/D/YYYY"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if line.strip().lower() == 'date':
            for j in range(i + 1, min(i + 10, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


def _extract_sonoco_recycling_date(text: str) -> Optional[str]:
    """Sonoco Recycling - Invoice Date: inline M/D/YYYY"""
    text = _normalize_text(text)
    m = re.search(r'Invoice Date:\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})', text, re.IGNORECASE)
    if m:
        return _parse_date_match(m, 'MDY')
    return None


def _extract_lake_area_disposal_date(text: str) -> Optional[str]:
    """Lake Area Disposal - STATEMENT DATE columnar MM/DD/YY"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if 'statement date' in line.lower():
            for j in range(i + 1, min(i + 5, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


def _extract_town_of_apple_valley_date(text: str) -> Optional[str]:
    """Town of Apple Valley - BILLING DATE wide columnar MM/DD/YY"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if 'billing date' in line.lower():
            for j in range(i + 1, min(i + 10, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


def _extract_mike_spano_and_sons_date(text: str) -> Optional[str]:
    """Mike Spano & Sons - Date columnar M/D/YYYY"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if line.strip().lower() == 'date':
            for j in range(i + 1, min(i + 10, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


# --- Tranche 54 ---

def _extract_joseph_j_runner_date(text: str) -> Optional[str]:
    """Joseph J. Runner - Invoice Date: wide columnar M/D/YYYY"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if 'invoice date' in line.lower():
            for j in range(i + 1, min(i + 5, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


def _extract_checksammy_date(text: str) -> Optional[str]:
    """Checksammy - Issued columnar Mon DD, YYYY"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if line.strip().lower() == 'issued':
            for j in range(i + 1, min(i + 5, len(lines))):
                m = re.match(r'^\s*([A-Za-z]{3,9})\s+(\d{1,2}),?\s*(\d{4})\s*$', lines[j].strip())
                if m:
                    month = MONTH_MAP.get(m.group(1).lower()[:3])
                    if month:
                        day, year = int(m.group(2)), int(m.group(3))
                        if _validate_date(month, day, year):
                            return _format_date(month, day, year)
    return None


def _extract_westport_funding_date(text: str) -> Optional[str]:
    """Westport Funding - Date columnar MM/DD/YYYY"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if line.strip().lower() == 'date':
            for j in range(i + 1, min(i + 5, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


def _extract_city_of_quincy_date(text: str) -> Optional[str]:
    """City of Quincy - Invoice Date: columnar MM/DD/YYYY"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if 'invoice date' in line.lower():
            for j in range(i + 1, min(i + 5, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


def _extract_solomon_container_service_date(text: str) -> Optional[str]:
    """Solomon Container Service - Date columnar MM/DD/YYYY"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if line.strip().lower() == 'date':
            for j in range(i + 1, min(i + 5, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


def _extract_copper_state_sanitation_date(text: str) -> Optional[str]:
    """Copper State Sanitation - DATE columnar MM/DD/YYYY"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if line.strip().upper() == 'DATE':
            for j in range(i + 1, min(i + 5, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


def _extract_windsor_sanitation_date(text: str) -> Optional[str]:
    """Windsor Sanitation - INVOICE DATE columnar M/D/YYYY"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if 'invoice date' in line.lower():
            for j in range(i + 1, min(i + 5, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


def _extract_opdenaker_trash_date(text: str) -> Optional[str]:
    """Opdenaker Trash - INVOICE DATE inline MM/DD/YYYY"""
    text = _normalize_text(text)
    m = re.search(r'INVOICE DATE\s+(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})', text, re.IGNORECASE)
    if m:
        return _parse_date_match(m, 'MDY')
    return None


def _extract_get_rid_of_it_waste_date(text: str) -> Optional[str]:
    """Get Rid Of It Waste - TrashBilling Weekday Mon DD, YYYY"""
    text = _normalize_text(text)
    m = re.search(r'(?:Mon|Tue|Wed|Thu|Fri|Sat|Sun)\s+([A-Za-z]{3})\s+(\d{1,2}),?\s*(\d{4})', text, re.IGNORECASE)
    if m:
        month = MONTH_MAP.get(m.group(1).lower()[:3])
        if month:
            day, year = int(m.group(2)), int(m.group(3))
            if _validate_date(month, day, year):
                return _format_date(month, day, year)
    return None


def _extract_tri_county_disposal_date(text: str) -> Optional[str]:
    """Tri County Disposal - Bill Date: wide columnar MM/DD/YYYY"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if 'bill date' in line.lower():
            for j in range(i + 1, min(i + 15, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


def _extract_absolute_services_date(text: str) -> Optional[str]:
    """Absolute Services - Invoice Date: inline MM/DD/YYYY"""
    text = _normalize_text(text)
    m = re.search(r'Invoice Date:\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})', text, re.IGNORECASE)
    if m:
        return _parse_date_match(m, 'MDY')
    return None


def _extract_jr_sanitation_date(text: str) -> Optional[str]:
    """J&R Sanitation - DATE inline MM/DD/YYYY"""
    text = _normalize_text(text)
    m = re.search(r'\bDATE\s+(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})', text, re.IGNORECASE)
    if m:
        return _parse_date_match(m, 'MDY')
    return None


# --- Tranche 55 ---

def _extract_california_waste_recovery_date(text: str) -> Optional[str]:
    """California Waste Recovery - Statement Date: reverse columnar MM/DD/YY"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if 'statement date' in line.lower():
            # Date is on the line BEFORE the label
            for j in range(max(0, i - 3), i):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


def _extract_ma_sanitation_date(text: str) -> Optional[str]:
    """MA Sanitation - Date columnar MM/DD/YYYY"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if line.strip().lower() == 'date':
            for j in range(i + 1, min(i + 5, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


def _extract_kadingers_date(text: str) -> Optional[str]:
    """Kadinger's - DATE wide columnar MM/DD/YYYY"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if line.strip().upper() == 'DATE':
            for j in range(i + 1, min(i + 12, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


def _extract_clarke_waste_solutions_date(text: str) -> Optional[str]:
    """Clarke Waste Solutions - SERVICE DATE columnar Mon DD, YYYY"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if 'service date' in line.lower():
            for j in range(i + 1, min(i + 5, len(lines))):
                m = re.match(r'^\s*([A-Za-z]{3,9})\s+(\d{1,2}),?\s*(\d{4})\s*$', lines[j].strip())
                if m:
                    month = MONTH_MAP.get(m.group(1).lower()[:3])
                    if month:
                        day, year = int(m.group(2)), int(m.group(3))
                        if _validate_date(month, day, year):
                            return _format_date(month, day, year)
    return None


def _extract_miller_and_sons_disposal_date(text: str) -> Optional[str]:
    """Miller and Sons Disposal - Invoice date: inline MM/DD/YYYY"""
    text = _normalize_text(text)
    m = re.search(r'Invoice date:\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})', text, re.IGNORECASE)
    if m:
        return _parse_date_match(m, 'MDY')
    return None


def _extract_norland_environmental_date(text: str) -> Optional[str]:
    """Norland Environmental - Date columnar M/D/YYYY"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if line.strip().lower() == 'date':
            for j in range(i + 1, min(i + 10, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


def _extract_marion_county_fiscal_court_date(text: str) -> Optional[str]:
    """Marion County Fiscal Court - DATES OF SERVICE M/DD/YYYY inline"""
    text = _normalize_text(text)
    m = re.search(r'DATES OF SERVICE\s+(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})', text, re.IGNORECASE)
    if m:
        return _parse_date_match(m, 'MDY')
    return None


def _extract_industrial_services_lincoln_date(text: str) -> Optional[str]:
    """Industrial Services Lincoln - STATEMENT DATE wide columnar MM/DD/YYYY"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if 'statement date' in line.lower():
            for j in range(i + 1, min(i + 10, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


def _extract_city_of_athens_ga_date(text: str) -> Optional[str]:
    """City of Athens GA - DATE: inline M/D/YYYY"""
    text = _normalize_text(text)
    m = re.search(r'\bDATE:\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})', text, re.IGNORECASE)
    if m:
        return _parse_date_match(m, 'MDY')
    return None


def _extract_oak_disposal_services_date(text: str) -> Optional[str]:
    """Oak Disposal Services - DATE inline MM/DD/YYYY"""
    text = _normalize_text(text)
    m = re.search(r'\bDATE\s+(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})', text, re.IGNORECASE)
    if m:
        return _parse_date_match(m, 'MDY')
    return None


def _extract_pederson_sanitation_date(text: str) -> Optional[str]:
    """Pederson Sanitation - DATE columnar Weekday Mon DD, YYYY"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if line.strip().upper() == 'DATE':
            for j in range(i + 1, min(i + 5, len(lines))):
                m = re.match(r'^\s*(?:Mon|Tue|Wed|Thu|Fri|Sat|Sun)\s+([A-Za-z]{3})\s+(\d{1,2}),?\s*(\d{4})\s*$', lines[j].strip(), re.IGNORECASE)
                if m:
                    month = MONTH_MAP.get(m.group(1).lower()[:3])
                    if month:
                        day, year = int(m.group(2)), int(m.group(3))
                        if _validate_date(month, day, year):
                            return _format_date(month, day, year)
    return None


def _extract_city_of_sierra_vista_date(text: str) -> Optional[str]:
    """City of Sierra Vista - Bill Date columnar MM/DD/YYYY"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if 'bill date' in line.lower():
            for j in range(i + 1, min(i + 5, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


# --- Tranche 56 ---

def _extract_vasco_road_landfill_date(text: str) -> Optional[str]:
    """Vasco Road Landfill - Invoice Date inline MM/DD/YYYY"""
    text = _normalize_text(text)
    m = re.search(r'Invoice Date\s+(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})', text, re.IGNORECASE)
    if m:
        return _parse_date_match(m, 'MDY')
    return None


def _extract_city_of_sevierville_date(text: str) -> Optional[str]:
    """City of Sevierville - Billing Date columnar M/D/YYYY"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if 'billing date' in line.lower():
            for j in range(i + 1, min(i + 5, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


def _extract_westbury_paper_stock_date(text: str) -> Optional[str]:
    """Westbury Paper Stock - INV DATE columnar MM/DD/YY"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if 'inv date' in line.lower():
            for j in range(i + 1, min(i + 5, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


def _extract_gibson_truck_service_date(text: str) -> Optional[str]:
    """Gibson Truck Service - Date columnar M/D/YYYY"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if line.strip().lower() == 'date':
            for j in range(i + 1, min(i + 5, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


def _extract_city_of_red_wing_date(text: str) -> Optional[str]:
    """City of Red Wing - BILLING DATE: wide columnar MM/DD/YYYY"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if 'billing date' in line.lower():
            for j in range(i + 1, min(i + 10, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


def _extract_southwest_sanitation_date(text: str) -> Optional[str]:
    """Southwest Sanitation - Date columnar MM/DD/YYYY"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if line.strip().lower() == 'date':
            for j in range(i + 1, min(i + 10, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


def _extract_bfi_waste_date(text: str) -> Optional[str]:
    """BFI Waste - TrashBilling Weekday Mon DD, YYYY"""
    text = _normalize_text(text)
    m = re.search(r'(?:Mon|Tue|Wed|Thu|Fri|Sat|Sun)\s+([A-Za-z]{3})\s+(\d{1,2}),?\s*(\d{4})', text, re.IGNORECASE)
    if m:
        month = MONTH_MAP.get(m.group(1).lower()[:3])
        if month:
            day, year = int(m.group(2)), int(m.group(3))
            if _validate_date(month, day, year):
                return _format_date(month, day, year)
    return None


def _extract_roberts_enterprises_date(text: str) -> Optional[str]:
    """Roberts Enterprises - TrashBilling Weekday Mon DD, YYYY"""
    text = _normalize_text(text)
    m = re.search(r'(?:Mon|Tue|Wed|Thu|Fri|Sat|Sun)\s+([A-Za-z]{3})\s+(\d{1,2}),?\s*(\d{4})', text, re.IGNORECASE)
    if m:
        month = MONTH_MAP.get(m.group(1).lower()[:3])
        if month:
            day, year = int(m.group(2)), int(m.group(3))
            if _validate_date(month, day, year):
                return _format_date(month, day, year)
    return None


def _extract_waste_express_date(text: str) -> Optional[str]:
    """Waste Express - DATE inline MM/DD/YYYY"""
    text = _normalize_text(text)
    m = re.search(r'\bDATE\s+(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})', text, re.IGNORECASE)
    if m:
        return _parse_date_match(m, 'MDY')
    return None


def _extract_snake_river_rubbish_date(text: str) -> Optional[str]:
    """Snake River Rubbish - TrashBilling Weekday Mon DD, YYYY"""
    text = _normalize_text(text)
    m = re.search(r'(?:Mon|Tue|Wed|Thu|Fri|Sat|Sun)\s+([A-Za-z]{3})\s+(\d{1,2}),?\s*(\d{4})', text, re.IGNORECASE)
    if m:
        month = MONTH_MAP.get(m.group(1).lower()[:3])
        if month:
            day, year = int(m.group(2)), int(m.group(3))
            if _validate_date(month, day, year):
                return _format_date(month, day, year)
    return None


def _extract_howies_trash_service_date(text: str) -> Optional[str]:
    """Howie's Trash Service - Invoice Date wide columnar M/DD/YY"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if 'invoice date' in line.lower():
            for j in range(i + 1, min(i + 5, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


def _extract_satellite_shelters_date(text: str) -> Optional[str]:
    """Satellite Shelters - Invoice Date: inline MM/DD/YYYY"""
    text = _normalize_text(text)
    m = re.search(r'Invoice Date:\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})', text, re.IGNORECASE)
    if m:
        return _parse_date_match(m, 'MDY')
    return None


# --- Tranche 57 ---

def _extract_city_of_buford_date(text: str) -> Optional[str]:
    """City of Buford - Billing Date columnar M/DD/YYYY"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if 'billing date' in line.lower():
            for j in range(i + 1, min(i + 10, len(lines))):
                m = re.search(r'(\d{1,2})[/\-](\d{1,2})[/\-](\d{4})', lines[j])
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


def _extract_orlando_recycling_date(text: str) -> Optional[str]:
    """Orlando Recycling - Date: Weekday Mon DD, YYYY inline"""
    text = _normalize_text(text)
    m = re.search(r'Date:\s*(?:Mon|Tue|Wed|Thu|Fri|Sat|Sun)\s+([A-Za-z]{3})\s+(\d{1,2}),?\s*(\d{4})', text, re.IGNORECASE)
    if m:
        month = MONTH_MAP.get(m.group(1).lower()[:3])
        if month:
            day, year = int(m.group(2)), int(m.group(3))
            if _validate_date(month, day, year):
                return _format_date(month, day, year)
    return None


def _extract_eds_disposal_date(text: str) -> Optional[str]:
    """Ed's Disposal - BILLING DATE: inline Month DD, YYYY"""
    text = _normalize_text(text)
    m = re.search(r'BILLING DATE:\s*([A-Za-z]+)\s+(\d{1,2}),?\s*(\d{4})', text, re.IGNORECASE)
    if m:
        month = MONTH_MAP.get(m.group(1).lower()[:3])
        if month:
            day, year = int(m.group(2)), int(m.group(3))
            if _validate_date(month, day, year):
                return _format_date(month, day, year)
    return None


def _extract_town_of_lake_park_date(text: str) -> Optional[str]:
    """Town of Lake Park - Due Date columnar M/D/YYYY"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if 'due date' in line.lower():
            for j in range(i + 1, min(i + 5, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


def _extract_wastevision_date(text: str) -> Optional[str]:
    """WasteVision - Invoice Date : columnar MM/DD/YYYY"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if 'invoice date' in line.lower():
            for j in range(i + 1, min(i + 5, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


def _extract_hilltopper_refuse_date(text: str) -> Optional[str]:
    """Hilltopper Refuse - DATE columnar M/DD/YYYY"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if 'date' in line.lower() and 'mm/dd' in line.lower():
            for j in range(i + 1, min(i + 5, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


def _extract_timberline_llc_date(text: str) -> Optional[str]:
    """Timberline LLC - Date columnar MM/DD/YYYY"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if line.strip().lower() == 'date':
            for j in range(i + 1, min(i + 5, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


def _extract_new_prague_sanitary_date(text: str) -> Optional[str]:
    """New Prague Sanitary - Invoice Date: inline MM/DD/YYYY"""
    text = _normalize_text(text)
    m = re.search(r'Invoice Date:\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})', text, re.IGNORECASE)
    if m:
        return _parse_date_match(m, 'MDY')
    return None


def _extract_olcese_waste_services_date(text: str) -> Optional[str]:
    """Olcese Waste Services - Invoice Date wide columnar M/DD/YY"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if 'invoice date' in line.lower():
            for j in range(i + 1, min(i + 10, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


def _extract_dillon_disposal_date(text: str) -> Optional[str]:
    """Dillon Disposal - Invoice Date columnar MM/DD/YYYY"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if 'invoice date' in line.lower():
            for j in range(i + 1, min(i + 5, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


def _extract_bnc_trash_service_date(text: str) -> Optional[str]:
    """B-N-C Trash Service - TrashBilling 'received on' format"""
    text = _normalize_text(text)
    m = re.search(r'received on (\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})', text, re.IGNORECASE)
    if m:
        return _parse_date_match(m, 'MDY')
    return None


def _extract_young_refuse_date(text: str) -> Optional[str]:
    """Young Refuse - TrashBilling Weekday Mon DD, YYYY"""
    text = _normalize_text(text)
    m = re.search(r'(?:Mon|Tue|Wed|Thu|Fri|Sat|Sun)\s+([A-Za-z]{3})\s+(\d{1,2}),?\s*(\d{4})', text, re.IGNORECASE)
    if m:
        month = MONTH_MAP.get(m.group(1).lower()[:3])
        if month:
            day, year = int(m.group(2)), int(m.group(3))
            if _validate_date(month, day, year):
                return _format_date(month, day, year)
    return None


# --- Tranche 58 ---

def _extract_city_of_cookeville_date(text: str) -> Optional[str]:
    """City of Cookeville - Bill Date columnar MM/DD/YYYY"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if 'bill date' in line.lower():
            for j in range(i + 1, min(i + 5, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


def _extract_blue_moon_date(text: str) -> Optional[str]:
    """Blue Moon - Date of issue columnar Month DD, YYYY"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if 'date of issue' in line.lower():
            for j in range(i + 1, min(i + 5, len(lines))):
                m = re.match(r'^\s*([A-Za-z]+)\s+(\d{1,2}),?\s*(\d{4})\s*$', lines[j].strip())
                if m:
                    month = MONTH_MAP.get(m.group(1).lower()[:3])
                    if month:
                        day, year = int(m.group(2)), int(m.group(3))
                        if _validate_date(month, day, year):
                            return _format_date(month, day, year)
    return None


def _extract_town_and_country_sanitation_date(text: str) -> Optional[str]:
    """Town & Country Sanitation - TrashBilling 'received on' format"""
    text = _normalize_text(text)
    m = re.search(r'received on (\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})', text, re.IGNORECASE)
    if m:
        return _parse_date_match(m, 'MDY')
    return None


def _extract_waste_reduction_sys_date(text: str) -> Optional[str]:
    """Waste Reduction Sys - DATE inline MM/DD/YYYY"""
    text = _normalize_text(text)
    m = re.search(r'\bDATE\s*:?\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})', text, re.IGNORECASE)
    if m:
        return _parse_date_match(m, 'MDY')
    return None


def _extract_eastern_waste_date(text: str) -> Optional[str]:
    """Eastern Waste - Invoice Date: inline MM/DD/YYYY"""
    text = _normalize_text(text)
    m = re.search(r'Invoice\s+Date\s*:?\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})', text, re.IGNORECASE)
    if m:
        return _parse_date_match(m, 'MDY')
    return None


def _extract_junk_solutions_date(text: str) -> Optional[str]:
    """Junk Solutions - Created inline Month DD, YYYY"""
    text = _normalize_text(text)
    m = re.search(r'Created\s*:?\s*([A-Za-z]+)\s+(\d{1,2}),?\s*(\d{4})', text, re.IGNORECASE)
    if m:
        month = MONTH_MAP.get(m.group(1).lower()[:3])
        if month:
            day, year = int(m.group(2)), int(m.group(3))
            if _validate_date(month, day, year):
                return _format_date(month, day, year)
    return None


def _extract_ace_equipment_company_date(text: str) -> Optional[str]:
    """Ace Equipment Company - DATE wide columnar MM/DD/YYYY"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if line.strip().upper() == 'DATE':
            for j in range(i + 1, min(i + 10, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


def _extract_dans_sanitation_date(text: str) -> Optional[str]:
    """Dan's Sanitation - Invoice Date: inline MM/DD/YYYY"""
    text = _normalize_text(text)
    m = re.search(r'Invoice\s+Date\s*:?\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})', text, re.IGNORECASE)
    if m:
        return _parse_date_match(m, 'MDY')
    return None


def _extract_ferrells_disposal_date(text: str) -> Optional[str]:
    """Ferrell's Disposal - Date columnar M/D/YYYY"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if line.strip().lower() == 'date':
            for j in range(i + 1, min(i + 5, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


def _extract_wayne_county_utah_date(text: str) -> Optional[str]:
    """Wayne County Utah - Date columnar MM/DD/YYYY (wide spacing)"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if line.strip().lower() == 'date':
            for j in range(i + 1, min(i + 6, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


def _extract_u_and_i_sanitation_date(text: str) -> Optional[str]:
    """U & I Sanitation - TrashBilling Weekday Mon DD, YYYY"""
    text = _normalize_text(text)
    m = re.search(r'(?:Mon|Tue|Wed|Thu|Fri|Sat|Sun)\s+([A-Za-z]{3})\s+(\d{1,2}),?\s*(\d{4})', text, re.IGNORECASE)
    if m:
        month = MONTH_MAP.get(m.group(1).lower()[:3])
        if month:
            day, year = int(m.group(2)), int(m.group(3))
            if _validate_date(month, day, year):
                return _format_date(month, day, year)
    return None


def _extract_c_and_s_disposal_date(text: str) -> Optional[str]:
    """C&S Disposal - Date columnar Month DD, YYYY"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if line.strip().lower() == 'date':
            for j in range(i + 1, min(i + 5, len(lines))):
                m = re.match(r'^\s*([A-Za-z]+)\s+(\d{1,2}),?\s*(\d{4})\s*$', lines[j].strip())
                if m:
                    month = MONTH_MAP.get(m.group(1).lower()[:3])
                    if month:
                        day, year = int(m.group(2)), int(m.group(3))
                        if _validate_date(month, day, year):
                            return _format_date(month, day, year)
    return None


# --- Tranche 59 ---

def _extract_city_of_somerset_date(text: str) -> Optional[str]:
    """City of Somerset - SERVICE FROM wide columnar MM/DD/YYYY"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if 'service from' in line.lower():
            for j in range(i + 1, min(i + 12, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


def _extract_tahoe_truckee_sierra_disposal_date(text: str) -> Optional[str]:
    """Tahoe Truckee Sierra Disposal - INVOICE DATE columnar M/DD/YYYY"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if 'invoice date' in line.lower():
            for j in range(i + 1, min(i + 5, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


def _extract_shamrock_waste_date(text: str) -> Optional[str]:
    """Shamrock Waste - Invoice date: columnar MM/DD/YYYY"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if 'invoice date' in line.lower():
            for j in range(i + 1, min(i + 6, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


def _extract_city_of_wolf_point_date(text: str) -> Optional[str]:
    """City of Wolf Point - Billed: inline MM/DD/YYYY"""
    text = _normalize_text(text)
    m = re.search(r'Billed:\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})', text, re.IGNORECASE)
    if m:
        return _parse_date_match(m, 'MDY')
    return None


def _extract_lex_serv_date(text: str) -> Optional[str]:
    """Lex Serv - Billing Date columnar Mon DD, YYYY"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if 'billing date' in line.lower():
            for j in range(i + 1, min(i + 5, len(lines))):
                m = re.match(r'^\s*([A-Za-z]{3})\s+(\d{1,2}),?\s*(\d{4})\s*$', lines[j].strip())
                if m:
                    month = MONTH_MAP.get(m.group(1).lower()[:3])
                    if month:
                        day, year = int(m.group(2)), int(m.group(3))
                        if _validate_date(month, day, year):
                            return _format_date(month, day, year)
    return None


def _extract_stewart_sanitation_date(text: str) -> Optional[str]:
    """Stewart Sanitation - Invoice Date wide columnar M/D/YYYY"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if 'invoice date' in line.lower():
            for j in range(i + 1, min(i + 6, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


def _extract_humboldt_county_landfill_date(text: str) -> Optional[str]:
    """Humboldt County Landfill - DATE: inline MM/DD/YYYY"""
    text = _normalize_text(text)
    m = re.search(r'\bDATE:\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})', text, re.IGNORECASE)
    if m:
        return _parse_date_match(m, 'MDY')
    return None


def _extract_olson_sanitation_date(text: str) -> Optional[str]:
    """Olson Sanitation - TrashBilling 'received on' format"""
    text = _normalize_text(text)
    m = re.search(r'received on (\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})', text, re.IGNORECASE)
    if m:
        return _parse_date_match(m, 'MDY')
    return None


def _extract_trash_rangers_date(text: str) -> Optional[str]:
    """Trash Rangers - Invoice Date columnar MM/DD/YYYY"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if 'invoice date' in line.lower():
            for j in range(i + 1, min(i + 8, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


def _extract_wingfield_service_date(text: str) -> Optional[str]:
    """Wingfield Service - TrashBilling Weekday Mon DD, YYYY"""
    text = _normalize_text(text)
    m = re.search(r'(?:Mon|Tue|Wed|Thu|Fri|Sat|Sun)\s+([A-Za-z]{3})\s+(\d{1,2}),?\s*(\d{4})', text, re.IGNORECASE)
    if m:
        month = MONTH_MAP.get(m.group(1).lower()[:3])
        if month:
            day, year = int(m.group(2)), int(m.group(3))
            if _validate_date(month, day, year):
                return _format_date(month, day, year)
    return None


def _extract_a_and_j_trash_date(text: str) -> Optional[str]:
    """A&J Trash - TrashBilling Weekday Mon DD, YYYY"""
    text = _normalize_text(text)
    m = re.search(r'(?:Mon|Tue|Wed|Thu|Fri|Sat|Sun)\s+([A-Za-z]{3})\s+(\d{1,2}),?\s*(\d{4})', text, re.IGNORECASE)
    if m:
        month = MONTH_MAP.get(m.group(1).lower()[:3])
        if month:
            day, year = int(m.group(2)), int(m.group(3))
            if _validate_date(month, day, year):
                return _format_date(month, day, year)
    return None


def _extract_city_of_rowlett_date(text: str) -> Optional[str]:
    """City of Rowlett - Bill Date columnar MM/DD/YYYY"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if 'bill date' in line.lower():
            for j in range(i + 1, min(i + 5, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


# --- Tranche 60 ---

def _extract_nisswa_sanitation_date(text: str) -> Optional[str]:
    """Nisswa Sanitation - Invoice Date columnar M/D/YY"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if 'invoice date' in line.lower():
            for j in range(i + 1, min(i + 5, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


def _extract_jackson_county_solid_waste_date(text: str) -> Optional[str]:
    """Jackson County Solid Waste - TrashBilling Weekday Mon DD, YYYY"""
    text = _normalize_text(text)
    m = re.search(r'(?:Mon|Tue|Wed|Thu|Fri|Sat|Sun)\s+([A-Za-z]{3})\s+(\d{1,2}),?\s*(\d{4})', text, re.IGNORECASE)
    if m:
        month = MONTH_MAP.get(m.group(1).lower()[:3])
        if month:
            day, year = int(m.group(2)), int(m.group(3))
            if _validate_date(month, day, year):
                return _format_date(month, day, year)
    return None


def _extract_southeast_waste_disposal_date(text: str) -> Optional[str]:
    """Southeast Waste Disposal - Date columnar MM/DD/YYYY"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if line.strip().lower() == 'date':
            for j in range(i + 1, min(i + 5, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


def _extract_gmen_environmental_date(text: str) -> Optional[str]:
    """Gmen Environmental - Invoice Date columnar M/DD/YY"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if 'invoice date' in line.lower():
            for j in range(i + 1, min(i + 5, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


def _extract_city_of_sidney_date(text: str) -> Optional[str]:
    """City of Sidney - CYCLE DATE columnar MM/DD/YY"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if 'cycle date' in line.lower():
            for j in range(i + 1, min(i + 5, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


def _extract_united_states_disposal_date(text: str) -> Optional[str]:
    """United States Disposal - Invoice Date: inline M/D/YYYY"""
    text = _normalize_text(text)
    m = re.search(r'Invoice\s+Date:\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})', text, re.IGNORECASE)
    if m:
        return _parse_date_match(m, 'MDY')
    return None


def _extract_north_country_disposal_date(text: str) -> Optional[str]:
    """North Country Disposal - Date wide columnar M/D/YY"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if line.strip().lower() == 'date':
            for j in range(i + 1, min(i + 10, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


def _extract_speedy_dump_date(text: str) -> Optional[str]:
    """Speedy Dump - DATE columnar Month DD, YYYY"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if line.strip().upper() == 'DATE':
            for j in range(i + 1, min(i + 5, len(lines))):
                m = re.match(r'^\s*([A-Za-z]+)\s+(\d{1,2}),?\s*(\d{4})\s*$', lines[j].strip())
                if m:
                    month = MONTH_MAP.get(m.group(1).lower()[:3])
                    if month:
                        day, year = int(m.group(2)), int(m.group(3))
                        if _validate_date(month, day, year):
                            return _format_date(month, day, year)
    return None


def _extract_mccullough_rubbish_date(text: str) -> Optional[str]:
    """McCullough Rubbish - Invoice Date: inline MM/DD/YYYY"""
    text = _normalize_text(text)
    m = re.search(r'Invoice\s+Date:\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})', text, re.IGNORECASE)
    if m:
        return _parse_date_match(m, 'MDY')
    return None


def _extract_kalamazoo_transfer_station_date(text: str) -> Optional[str]:
    """Kalamazoo Transfer Station - Invoice Date inline MM/DD/YYYY"""
    text = _normalize_text(text)
    m = re.search(r'Invoice\s+Date\s+(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})', text, re.IGNORECASE)
    if m:
        return _parse_date_match(m, 'MDY')
    return None


def _extract_a_and_c_waste_collection_date(text: str) -> Optional[str]:
    """A&C Waste Collection - Payment date columnar MM/DD/YYYY"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if 'payment date' in line.lower():
            for j in range(i + 1, min(i + 8, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


def _extract_gilton_solid_waste_date(text: str) -> Optional[str]:
    """Gilton Solid Waste - STMT DATE inline M/DD/YYYY"""
    text = _normalize_text(text)
    # Date appears inline on same line as account number, first date after account info
    m = re.search(r'\d{6,}-\d+\s+\S+-\S+\s+(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})', text)
    if m:
        return _parse_date_match(m, 'MDY')
    return None


# --- Tranche 61 ---

def _extract_native_dynamics_date(text: str) -> Optional[str]:
    """Native Dynamics - DATE wide columnar MM/DD/YYYY"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if line.strip().upper() == 'DATE':
            for j in range(i + 1, min(i + 10, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


def _extract_tds_llc_date(text: str) -> Optional[str]:
    """TDS LLC - TrashBilling 'received on' format"""
    text = _normalize_text(text)
    m = re.search(r'received on (\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})', text, re.IGNORECASE)
    if m:
        return _parse_date_match(m, 'MDY')
    return None


def _extract_bright_disposal_services_date(text: str) -> Optional[str]:
    """Bright Disposal Services - Date: Weekday Mon DD, YYYY inline"""
    text = _normalize_text(text)
    m = re.search(r'Date:\s*(?:Mon|Tue|Wed|Thu|Fri|Sat|Sun)\s+([A-Za-z]{3})\s+(\d{1,2}),?\s*(\d{4})', text, re.IGNORECASE)
    if m:
        month = MONTH_MAP.get(m.group(1).lower()[:3])
        if month:
            day, year = int(m.group(2)), int(m.group(3))
            if _validate_date(month, day, year):
                return _format_date(month, day, year)
    return None


def _extract_serv_wel_disposal_date(text: str) -> Optional[str]:
    """Serv-Wel Disposal - Date columnar M/D/YYYY"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if line.strip().lower() == 'date':
            for j in range(i + 1, min(i + 5, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


def _extract_city_of_rockhill_date(text: str) -> Optional[str]:
    """City of Rockhill - Due Date columnar Mon-DD-YYYY"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if 'due date' in line.lower():
            for j in range(i + 1, min(i + 5, len(lines))):
                m = re.match(r'^\s*([A-Za-z]{3})-(\d{1,2})-(\d{4})\s*$', lines[j].strip())
                if m:
                    month = MONTH_MAP.get(m.group(1).lower()[:3])
                    if month:
                        day, year = int(m.group(2)), int(m.group(3))
                        if _validate_date(month, day, year):
                            return _format_date(month, day, year)
    return None


def _extract_all_states_services_date(text: str) -> Optional[str]:
    """All States Services - Invoice Date: inline M/D/YYYY"""
    text = _normalize_text(text)
    m = re.search(r'Invoice\s+Date:\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})', text, re.IGNORECASE)
    if m:
        return _parse_date_match(m, 'MDY')
    return None


def _extract_ogborne_hauling_date(text: str) -> Optional[str]:
    """Ogborne Hauling - DATE wide columnar MM/DD/YYYY"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if line.strip().upper() == 'DATE':
            for j in range(i + 1, min(i + 10, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


def _extract_innovative_trash_service_date(text: str) -> Optional[str]:
    """Innovative Trash Service - Issued columnar Mon DD, YYYY"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if line.strip().lower() == 'issued':
            for j in range(i + 1, min(i + 5, len(lines))):
                m = re.match(r'^\s*([A-Za-z]{3})\s+(\d{1,2}),?\s*(\d{4})\s*$', lines[j].strip())
                if m:
                    month = MONTH_MAP.get(m.group(1).lower()[:3])
                    if month:
                        day, year = int(m.group(2)), int(m.group(3))
                        if _validate_date(month, day, year):
                            return _format_date(month, day, year)
    return None


def _extract_golden_valley_disposal_date(text: str) -> Optional[str]:
    """Golden Valley Disposal - DATE columnar M/D/YYYY"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if line.strip().upper() == 'DATE':
            for j in range(i + 1, min(i + 5, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


def _extract_guidos_services_date(text: str) -> Optional[str]:
    """Guido's Services - DATE columnar MM/DD/YYYY"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if line.strip().upper() == 'DATE':
            for j in range(i + 1, min(i + 5, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


def _extract_waste_masters_date(text: str) -> Optional[str]:
    """Waste Masters - DATE reverse columnar Mon-DD-YY"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if line.strip().upper() == 'DATE':
            # Date value is BEFORE the DATE label
            for j in range(max(0, i - 5), i):
                m = re.match(r'^\s*([A-Za-z]{3})-(\d{1,2})-(\d{2,4})\s*$', lines[j].strip())
                if m:
                    month = MONTH_MAP.get(m.group(1).lower()[:3])
                    if month:
                        day, year = int(m.group(2)), int(m.group(3))
                        if _validate_date(month, day, year):
                            return _format_date(month, day, year)
    return None


def _extract_pacific_sanitation_co_date(text: str) -> Optional[str]:
    """Pacific Sanitation Co - DUE DATE columnar MM/DD/YYYY"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if 'due date' in line.lower():
            for j in range(i + 1, min(i + 5, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


# --- Tranche 62 ---

def _extract_overton_recycling_date(text: str) -> Optional[str]:
    """Overton Recycling - TrashBilling 'received on' format"""
    text = _normalize_text(text)
    m = re.search(r'received on (\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})', text, re.IGNORECASE)
    if m:
        return _parse_date_match(m, 'MDY')
    return None


def _extract_helgerson_property_maintenance_date(text: str) -> Optional[str]:
    """Helgerson Property Maintenance - Invoice date: inline MM/DD/YYYY"""
    text = _normalize_text(text)
    m = re.search(r'Invoice\s+date:\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})', text, re.IGNORECASE)
    if m:
        return _parse_date_match(m, 'MDY')
    return None


def _extract_okon_recycling_date(text: str) -> Optional[str]:
    """Okon Recycling - Invoice Date: reverse columnar M/D/YY"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if 'invoice date' in line.lower():
            # Date value is BEFORE the Invoice Date label
            for j in range(max(0, i - 3), i):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


def _extract_waste_services_inc_date(text: str) -> Optional[str]:
    """Waste Services Inc - INV DATE columnar MM/DD/YY"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if 'inv date' in line.lower():
            for j in range(i + 1, min(i + 5, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


def _extract_fogles_date(text: str) -> Optional[str]:
    """Fogle's - INVOICE DATE columnar MM/DD/YYYY"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if 'invoice date' in line.lower():
            for j in range(i + 1, min(i + 5, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


def _extract_wayn_os_disposal_service_date(text: str) -> Optional[str]:
    """Wayn-O's Disposal Service - Date columnar M/DD/YYYY"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if line.strip().lower() == 'date':
            for j in range(i + 1, min(i + 5, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


def _extract_solid_waste_services_wv_date(text: str) -> Optional[str]:
    """Solid Waste Services WV - INVOICE DATE wide columnar Mon-DD-YYYY"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if 'invoice date' in line.lower():
            for j in range(i + 1, min(i + 10, len(lines))):
                m = re.match(r'^\s*([A-Za-z]{3})-(\d{1,2})-(\d{4})\s*$', lines[j].strip())
                if m:
                    month = MONTH_MAP.get(m.group(1).lower()[:3])
                    if month:
                        day, year = int(m.group(2)), int(m.group(3))
                        if _validate_date(month, day, year):
                            return _format_date(month, day, year)
    return None


def _extract_dyersburg_gas_and_water_date(text: str) -> Optional[str]:
    """Dyersburg Gas & Water - SERVICE FROM columnar MM-DD-YY"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if 'service from' in line.lower():
            for j in range(i + 1, min(i + 5, len(lines))):
                m = re.match(r'^\s*(\d{1,2})-(\d{1,2})-(\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


def _extract_volunteer_disposal_west_date(text: str) -> Optional[str]:
    """Volunteer Disposal West - TrashBilling Weekday Mon DD, YYYY"""
    text = _normalize_text(text)
    m = re.search(r'(?:Mon|Tue|Wed|Thu|Fri|Sat|Sun)\s+([A-Za-z]{3})\s+(\d{1,2}),?\s*(\d{4})', text, re.IGNORECASE)
    if m:
        month = MONTH_MAP.get(m.group(1).lower()[:3])
        if month:
            day, year = int(m.group(2)), int(m.group(3))
            if _validate_date(month, day, year):
                return _format_date(month, day, year)
    return None


def _extract_certified_enterprises_date(text: str) -> Optional[str]:
    """Certified Enterprises - Inv Date wide columnar MM/DD/YYYY"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if 'inv date' in line.lower():
            for j in range(i + 1, min(i + 6, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


def _extract_becker_complete_date(text: str) -> Optional[str]:
    """Becker Complete - DATE columnar MM/DD/YYYY"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if line.strip().upper() == 'DATE':
            for j in range(i + 1, min(i + 5, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


def _extract_reliable_paper_date(text: str) -> Optional[str]:
    """Reliable Paper - Invoice Date report format M/D/YYYY"""
    text = _normalize_text(text)
    # Find first date after customer identifier in aged report
    m = re.search(r'WASTEOL\S*\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})', text, re.IGNORECASE)
    if m:
        return _parse_date_match(m, 'MDY')
    return None


# --- Tranche 63 ---

def _extract_skyhook_date(text: str) -> Optional[str]:
    """Skyhook - Invoice date: inline MM/DD/YYYY"""
    text = _normalize_text(text)
    m = re.search(r'Invoice\s+date:\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})', text, re.IGNORECASE)
    if m:
        return _parse_date_match(m, 'MDY')
    return None


def _extract_city_of_fort_myers_date(text: str) -> Optional[str]:
    """City of Fort Myers - BILL DATE: inline MM/DD/YY"""
    text = _normalize_text(text)
    m = re.search(r'BILL\s+DATE:\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})', text, re.IGNORECASE)
    if m:
        return _parse_date_match(m, 'MDY')
    return None


def _extract_city_of_douglasville_date(text: str) -> Optional[str]:
    """City of Douglasville - DUE DATE columnar MM/DD/YY"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if 'due date' in line.lower():
            for j in range(i + 1, min(i + 5, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


def _extract_kopchos_sanitation_date(text: str) -> Optional[str]:
    """Kopchos Sanitation - STATEMENT DATE columnar MM/DD/YYYY"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if 'statement date' in line.lower():
            for j in range(i + 1, min(i + 5, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


def _extract_metech_recycling_date(text: str) -> Optional[str]:
    """Metech Recycling - DATE inline MM/DD/YYYY"""
    text = _normalize_text(text)
    m = re.search(r'\bDATE\s+(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})', text, re.IGNORECASE)
    if m:
        return _parse_date_match(m, 'MDY')
    return None


def _extract_madden_sanitation_date(text: str) -> Optional[str]:
    """Madden Sanitation - TrashBilling 'received on' format"""
    text = _normalize_text(text)
    m = re.search(r'received on (\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})', text, re.IGNORECASE)
    if m:
        return _parse_date_match(m, 'MDY')
    return None


def _extract_american_eagle_waste_date(text: str) -> Optional[str]:
    """American Eagle Waste - BILL DATE columnar MM/DD/YY"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if 'bill date' in line.lower():
            for j in range(i + 1, min(i + 5, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


def _extract_reno_forklift_date(text: str) -> Optional[str]:
    """Reno Forklift - Statement Date columnar MM/DD/YYYY"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if line.strip().lower() == 'date':
            for j in range(i + 1, min(i + 5, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


def _extract_dc_waste_date(text: str) -> Optional[str]:
    """DC Waste - Invoice Date columnar M/D/YY"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if 'invoice date' in line.lower():
            for j in range(i + 1, min(i + 5, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


def _extract_south_san_francisco_scavenger_date(text: str) -> Optional[str]:
    """South San Francisco Scavenger - Invoice Date columnar M/D/YYYY"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if 'invoice date' in line.lower():
            for j in range(i + 1, min(i + 6, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


def _extract_shulars_trash_service_date(text: str) -> Optional[str]:
    """Shular's Trash Service - DATE columnar Weekday Mon DD, YYYY"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if line.strip().upper() == 'DATE':
            for j in range(i + 1, min(i + 5, len(lines))):
                m = re.match(r'^\s*(?:Mon|Tue|Wed|Thu|Fri|Sat|Sun)\s+([A-Za-z]{3})\s+(\d{1,2}),?\s*(\d{4})\s*$', lines[j].strip())
                if m:
                    month = MONTH_MAP.get(m.group(1).lower()[:3])
                    if month:
                        day, year = int(m.group(2)), int(m.group(3))
                        if _validate_date(month, day, year):
                            return _format_date(month, day, year)
    return None


def _extract_nooksack_valley_disposal_date(text: str) -> Optional[str]:
    """Nooksack Valley Disposal - Billing Date: inline MM/DD/YY"""
    text = _normalize_text(text)
    m = re.search(r'Billing\s+Date:\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})', text, re.IGNORECASE)
    if m:
        return _parse_date_match(m, 'MDY')
    return None


# --- Tranche 64 ---

def _extract_hiltz_date(text: str) -> Optional[str]:
    """Hiltz - DATE columnar Mon-DD-YY"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if line.strip().upper() == 'DATE':
            for j in range(i + 1, min(i + 5, len(lines))):
                m = re.match(r'^\s*([A-Za-z]{3})-(\d{1,2})-(\d{2,4})\s*$', lines[j].strip())
                if m:
                    month = MONTH_MAP.get(m.group(1).lower()[:3])
                    if month:
                        day, year = int(m.group(2)), int(m.group(3))
                        if _validate_date(month, day, year):
                            return _format_date(month, day, year)
    return None


def _extract_city_of_willcox_date(text: str) -> Optional[str]:
    """City of Willcox - Billing Date wide columnar MM-DD-YYYY"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if 'billing date' in line.lower():
            for j in range(i + 1, min(i + 15, len(lines))):
                m = re.match(r'^\s*(\d{1,2})-(\d{1,2})-(\d{4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


def _extract_anchor_technical_date(text: str) -> Optional[str]:
    """Anchor Technical - Date columnar M/DD/YYYY"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if line.strip().lower() == 'date':
            for j in range(i + 1, min(i + 5, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


def _extract_clarks_disposal_date(text: str) -> Optional[str]:
    """Clark's Disposal - TrashBilling Weekday Mon DD, YYYY"""
    text = _normalize_text(text)
    m = re.search(r'(?:Mon|Tue|Wed|Thu|Fri|Sat|Sun)\s+([A-Za-z]{3})\s+(\d{1,2}),?\s*(\d{4})', text, re.IGNORECASE)
    if m:
        month = MONTH_MAP.get(m.group(1).lower()[:3])
        if month:
            day, year = int(m.group(2)), int(m.group(3))
            if _validate_date(month, day, year):
                return _format_date(month, day, year)
    return None


def _extract_missoula_compost_date(text: str) -> Optional[str]:
    """Missoula Compost - TrashBilling 'received on' format"""
    text = _normalize_text(text)
    m = re.search(r'received on (\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})', text, re.IGNORECASE)
    if m:
        return _parse_date_match(m, 'MDY')
    return None


def _extract_recycling_center_of_north_dakota_date(text: str) -> Optional[str]:
    """Recycling Center of North Dakota - Date columnar M/DD/YYYY"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if line.strip().lower() == 'date':
            for j in range(i + 1, min(i + 8, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


def _extract_gear_for_waste_date(text: str) -> Optional[str]:
    """Gear For Waste - Date columnar M/D/YYYY"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if line.strip().lower() == 'date':
            for j in range(i + 1, min(i + 6, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


def _extract_tom_danley_disposal_date(text: str) -> Optional[str]:
    """Tom Danley Disposal - DATE columnar MM/DD/YYYY"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if line.strip().upper() == 'DATE':
            for j in range(i + 1, min(i + 5, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


def _extract_triple_h_enterprises_date(text: str) -> Optional[str]:
    """Triple H Enterprises - Date columnar M/D/YYYY"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if line.strip().lower() == 'date':
            for j in range(i + 1, min(i + 5, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


def _extract_waste_disposal_az_date(text: str) -> Optional[str]:
    """Waste Disposal AZ - Date Billed: inline MM/DD/YYYY"""
    text = _normalize_text(text)
    m = re.search(r'Date\s+Billed:\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})', text, re.IGNORECASE)
    if m:
        return _parse_date_match(m, 'MDY')
    return None


def _extract_kirby_sanitation_date(text: str) -> Optional[str]:
    """Kirby Sanitation - INVOICE DATE columnar M/DD/YYYY"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if 'invoice date' in line.lower():
            for j in range(i + 1, min(i + 5, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


def _extract_winston_sanitary_date(text: str) -> Optional[str]:
    """Winston Sanitary - STATEMENT DATE columnar MM/DD/YYYY"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if 'statement date' in line.lower():
            for j in range(i + 1, min(i + 5, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


# --- Tranche 65 ---

def _extract_top_of_the_line_dumpsters_date(text: str) -> Optional[str]:
    """Top of the Line Dumpsters - Invoice Date columnar M/D/YYYY"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if 'invoice date' in line.lower():
            for j in range(i + 1, min(i + 5, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


def _extract_chisago_lakes_sanitation_date(text: str) -> Optional[str]:
    """Chisago Lakes Sanitation - INV DATE columnar MM/DD/YY"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if 'inv date' in line.lower():
            for j in range(i + 1, min(i + 5, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


def _extract_dedicated_dumpster_service_date(text: str) -> Optional[str]:
    """Dedicated Dumpster Service - Date: Weekday Mon DD, YYYY inline"""
    text = _normalize_text(text)
    m = re.search(r'Date:\s*(?:Mon|Tue|Wed|Thu|Fri|Sat|Sun)\s+([A-Za-z]{3})\s+(\d{1,2}),?\s*(\d{4})', text, re.IGNORECASE)
    if m:
        month = MONTH_MAP.get(m.group(1).lower()[:3])
        if month:
            day, year = int(m.group(2)), int(m.group(3))
            if _validate_date(month, day, year):
                return _format_date(month, day, year)
    return None


def _extract_citrus_county_utilities_date(text: str) -> Optional[str]:
    """Citrus County Utilities - Invoice Date: wide columnar MM/DD/YYYY"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if 'invoice date' in line.lower():
            for j in range(i + 1, min(i + 15, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


def _extract_pendleton_sanitary_service_date(text: str) -> Optional[str]:
    """Pendleton Sanitary Service - STATEMENT DATE columnar MM/DD/YYYY"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if 'statement date' in line.lower():
            for j in range(i + 1, min(i + 5, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


def _extract_united_waste_systems_date(text: str) -> Optional[str]:
    """United Waste Systems - Invoice Date: columnar MM/DD/YYYY"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if 'invoice date' in line.lower():
            for j in range(i + 1, min(i + 6, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


def _extract_cogent_waste_solutions_date(text: str) -> Optional[str]:
    """Cogent Waste Solutions - Invoice Date reverse columnar M/D/YY"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if 'invoice date' in line.lower():
            # Date value is BEFORE the Invoice Date label
            for j in range(max(0, i - 3), i):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


def _extract_gtx_gainsborough_waste_date(text: str) -> Optional[str]:
    """GTX Gainsborough Waste - Date columnar M/D/YYYY"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if line.strip().lower() == 'date':
            for j in range(i + 1, min(i + 8, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


def _extract_waste_disposal_services_date(text: str) -> Optional[str]:
    """Waste Disposal Services - TrashBilling 'received on' format"""
    text = _normalize_text(text)
    m = re.search(r'received on (\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})', text, re.IGNORECASE)
    if m:
        return _parse_date_match(m, 'MDY')
    return None


def _extract_town_of_gardnerville_date(text: str) -> Optional[str]:
    """Town of Gardnerville - DATE MAILED columnar MM/DD/YY"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if 'date mailed' in line.lower():
            for j in range(i + 1, min(i + 5, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


def _extract_step_up_disposals_date(text: str) -> Optional[str]:
    """Step Up Disposals - Invoice Date: inline MM/DD/YYYY"""
    text = _normalize_text(text)
    m = re.search(r'Invoice\s+Date:\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})', text, re.IGNORECASE)
    if m:
        return _parse_date_match(m, 'MDY')
    return None


def _extract_city_of_madisonville_date(text: str) -> Optional[str]:
    """City of Madisonville - Billing Date columnar M/DD/YY (second date on line)"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if 'billing date' in line.lower():
            for j in range(i + 1, min(i + 5, len(lines))):
                # Two dates on same line - extract second one
                m = re.search(r'\d{1,2}[/\-]\d{1,2}[/\-]\d{2,4}\s+(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})', lines[j])
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


# --- Tranche 66 ---
def _extract_valley_waste_service_date(text: str) -> Optional[str]:
    """Valley Waste Service - Invoice Date: MM/DD/YYYY inline"""
    text = _normalize_text(text)
    m = re.search(r'Invoice\s+Date:\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})', text, re.IGNORECASE)
    if m:
        return _parse_date_match(m, 'MDY')
    return None


def _extract_salt_river_pima_date(text: str) -> Optional[str]:
    """Salt River Pima - Invoice Date columnar MM/DD/YYYY"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if 'invoice date' in line.lower():
            for j in range(i + 1, min(i + 8, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


def _extract_best_pick_disposal_date(text: str) -> Optional[str]:
    """Best Pick Disposal - INVOICE DATE MM/DD/YYYY inline"""
    text = _normalize_text(text)
    m = re.search(r'INVOICE\s+DATE\s+(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})', text, re.IGNORECASE)
    if m:
        return _parse_date_match(m, 'MDY')
    return None


def _extract_national_waste_and_disposal_date(text: str) -> Optional[str]:
    """National Waste & Disposal - INVOICE DATE columnar M/D/YYYY"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if 'invoice date' in line.lower():
            for j in range(i + 1, min(i + 5, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


def _extract_mds_waste_date(text: str) -> Optional[str]:
    """MDS Waste - TrashBilling Weekday Mon DD, YYYY format"""
    text = _normalize_text(text)
    m = re.search(r'(?:Mon|Tue|Wed|Thu|Fri|Sat|Sun)\s+([A-Za-z]{3})\s+(\d{1,2}),?\s+(\d{4})', text)
    if m:
        month = MONTH_MAP.get(m.group(1).lower()[:3])
        if month:
            day, year = int(m.group(2)), int(m.group(3))
            if _validate_date(month, day, year):
                return _format_date(month, day, year)
    return None


def _extract_abes_trash_service_date(text: str) -> Optional[str]:
    """Abe's Trash Service - Invoice Date reverse columnar MM/DD/YY"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if 'invoice date' in line.lower():
            for j in range(max(0, i - 3), i):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


def _extract_island_refuse_date(text: str) -> Optional[str]:
    """Island Refuse - DATE MM/DD/YYYY inline"""
    text = _normalize_text(text)
    m = re.search(r'\bDATE\s+(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})', text, re.IGNORECASE)
    if m:
        return _parse_date_match(m, 'MDY')
    return None


def _extract_city_of_dickinson_date(text: str) -> Optional[str]:
    """City of Dickinson - BILLING START DATE columnar Month DD, YYYY"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if 'billing start date' in line.lower():
            for j in range(i + 1, min(i + 5, len(lines))):
                m = re.match(r'^\s*([A-Za-z]+)\s+(\d{1,2}),?\s+(\d{4})\s*$', lines[j].strip())
                if m:
                    month = MONTH_MAP.get(m.group(1).lower()[:3])
                    if month:
                        day, year = int(m.group(2)), int(m.group(3))
                        if _validate_date(month, day, year):
                            return _format_date(month, day, year)
    return None


def _extract_snake_river_dispose_all_date(text: str) -> Optional[str]:
    """Snake River Dispose-All - Date columnar M/D/YYYY"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if line.strip().lower() == 'date':
            for j in range(i + 1, min(i + 5, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


def _extract_maui_disposal_co_date(text: str) -> Optional[str]:
    """Maui Disposal Co - Payment Date columnar Month DD, YYYY"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if 'payment date' in line.lower():
            for j in range(i + 1, min(i + 5, len(lines))):
                m = re.match(r'^\s*([A-Za-z]+)\s+(\d{1,2}),?\s+(\d{4})', lines[j].strip())
                if m:
                    month = MONTH_MAP.get(m.group(1).lower()[:3])
                    if month:
                        day, year = int(m.group(2)), int(m.group(3))
                        if _validate_date(month, day, year):
                            return _format_date(month, day, year)
    return None


def _extract_matts_sanitation_date(text: str) -> Optional[str]:
    """Matt's Sanitation - STATEMENT MM-DD-YYYY format"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines[:10]):
        if 'statement' in line.lower():
            for j in range(max(0, i - 2), min(i + 3, len(lines))):
                m = re.search(r'(\d{1,2})-(\d{1,2})-(\d{4})', lines[j])
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


def _extract_hughes_and_sons_date(text: str) -> Optional[str]:
    """Hughes & Sons - Invoice Date: columnar MM/DD/YYYY"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if 'invoice date' in line.lower():
            for j in range(i + 1, min(i + 6, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


# --- Tranche 67 ---
def _extract_compostnow_date(text: str) -> Optional[str]:
    """CompostNow - DATE columnar MM/DD/YYYY"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if line.strip().upper() == 'DATE':
            for j in range(i + 1, min(i + 5, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


def _extract_martins_trash_service_date(text: str) -> Optional[str]:
    """Martin's Trash Service - TrashBilling Weekday Mon DD, YYYY format"""
    text = _normalize_text(text)
    m = re.search(r'(?:Mon|Tue|Wed|Thu|Fri|Sat|Sun)\s+([A-Za-z]{3})\s+(\d{1,2}),?\s+(\d{4})', text)
    if m:
        month = MONTH_MAP.get(m.group(1).lower()[:3])
        if month:
            day, year = int(m.group(2)), int(m.group(3))
            if _validate_date(month, day, year):
                return _format_date(month, day, year)
    return None


def _extract_brothers_disposal_date(text: str) -> Optional[str]:
    """Brothers Disposal - received on M/DD/YYYY (TrashBilling)"""
    text = _normalize_text(text)
    m = re.search(r'received\s+on\s+(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})', text, re.IGNORECASE)
    if m:
        return _parse_date_match(m, 'MDY')
    return None


def _extract_sutherlin_sanitary_date(text: str) -> Optional[str]:
    """Sutherlin Sanitary - Bill Date columnar Month DD, YYYY"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if 'bill date' in line.lower():
            for j in range(i + 1, min(i + 5, len(lines))):
                m = re.match(r'^\s*([A-Za-z]+)\s+(\d{1,2}),?\s+(\d{4})\s*$', lines[j].strip())
                if m:
                    month = MONTH_MAP.get(m.group(1).lower()[:3])
                    if month:
                        day, year = int(m.group(2)), int(m.group(3))
                        if _validate_date(month, day, year):
                            return _format_date(month, day, year)
    return None


def _extract_goode_companies_date(text: str) -> Optional[str]:
    """Goode Companies - INV DATE columnar MM/DD/YY"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if 'inv date' in line.lower():
            for j in range(i + 1, min(i + 5, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


def _extract_cressman_sanitation_date(text: str) -> Optional[str]:
    """Cressman Sanitation - TrashBilling Weekday Mon DD, YYYY format"""
    text = _normalize_text(text)
    m = re.search(r'(?:Mon|Tue|Wed|Thu|Fri|Sat|Sun)\s+([A-Za-z]{3})\s+(\d{1,2}),?\s+(\d{4})', text)
    if m:
        month = MONTH_MAP.get(m.group(1).lower()[:3])
        if month:
            day, year = int(m.group(2)), int(m.group(3))
            if _validate_date(month, day, year):
                return _format_date(month, day, year)
    return None


def _extract_sonoran_ranch_date(text: str) -> Optional[str]:
    """Sonoran Ranch - Issued Date: columnar Mon D, YYYY"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if 'issued date' in line.lower():
            for j in range(i + 1, min(i + 5, len(lines))):
                m = re.match(r'^\s*([A-Za-z]{3})\s+(\d{1,2}),?\s+(\d{4})\s*$', lines[j].strip())
                if m:
                    month = MONTH_MAP.get(m.group(1).lower()[:3])
                    if month:
                        day, year = int(m.group(2)), int(m.group(3))
                        if _validate_date(month, day, year):
                            return _format_date(month, day, year)
    return None


def _extract_franklin_pallet_date(text: str) -> Optional[str]:
    """Franklin Pallet - Invoice Date: DD Month YYYY inline"""
    text = _normalize_text(text)
    m = re.search(r'Invoice\s+Date:\s*(\d{1,2})\s+([A-Za-z]+)\s+(\d{4})', text, re.IGNORECASE)
    if m:
        day = int(m.group(1))
        month = MONTH_MAP.get(m.group(2).lower()[:3])
        year = int(m.group(3))
        if month and _validate_date(month, day, year):
            return _format_date(month, day, year)
    return None


def _extract_city_of_culver_city_date(text: str) -> Optional[str]:
    """City of Culver City - Month DD, YYYY near date header"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines[:15]):
        m = re.match(r'^\s*([A-Za-z]+)\s+(\d{1,2}),?\s+(\d{4})\s*$', line.strip())
        if m:
            month = MONTH_MAP.get(m.group(1).lower()[:3])
            if month:
                day, year = int(m.group(2)), int(m.group(3))
                if _validate_date(month, day, year):
                    return _format_date(month, day, year)
    return None


def _extract_garland_county_landfill_date(text: str) -> Optional[str]:
    """Garland County Landfill - Invoice Date: MM/DD/YYYY inline"""
    text = _normalize_text(text)
    m = re.search(r'Invoice\s+Date:\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})', text, re.IGNORECASE)
    if m:
        return _parse_date_match(m, 'MDY')
    return None


def _extract_olathe_kansas_date(text: str) -> Optional[str]:
    """Olathe Kansas - Statement Date columnar MM/DD/YYYY"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if 'statement date' in line.lower():
            for j in range(i + 1, min(i + 5, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


def _extract_r_and_r_midwest_date(text: str) -> Optional[str]:
    """R & R Midwest - DATE MM/DD/YYYY inline"""
    text = _normalize_text(text)
    m = re.search(r'\bDATE\s+(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})', text, re.IGNORECASE)
    if m:
        return _parse_date_match(m, 'MDY')
    return None


# --- Tranche 68 ---
def _extract_ingrum_waste_disposal_date(text: str) -> Optional[str]:
    """Ingrum Waste Disposal - DATE reverse columnar Mon-DD-YY"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if line.strip().upper() == 'DATE':
            for j in range(max(0, i - 5), i):
                m = re.match(r'^\s*([A-Za-z]{3})-(\d{2})-(\d{2})\s*$', lines[j].strip())
                if m:
                    month = MONTH_MAP.get(m.group(1).lower()[:3])
                    if month:
                        day, year = int(m.group(2)), int(m.group(3))
                        if year < 50:
                            year += 2000
                        else:
                            year += 1900
                        if _validate_date(month, day, year):
                            return _format_date(month, day, year)
    return None


def _extract_impact_environmental_date(text: str) -> Optional[str]:
    """Impact Environmental - M/DD/YYYY near top of invoice"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines[:15]):
        m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{4})\s*$', line.strip())
        if m:
            return _parse_date_match(m, 'MDY')
    return None


def _extract_jamaica_ash_and_rubbish_date(text: str) -> Optional[str]:
    """Jamaica Ash & Rubbish - INV DATE columnar MM/DD/YY"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if 'inv date' in line.lower():
            for j in range(i + 1, min(i + 5, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


def _extract_capital_city_date(text: str) -> Optional[str]:
    """Capital City - Invoice Date: columnar MM/DD/YYYY"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if 'invoice date' in line.lower():
            for j in range(i + 1, min(i + 5, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


def _extract_ab_8_waste_solutions_date(text: str) -> Optional[str]:
    """AB-8 Waste Solutions - Date columnar M/D/YYYY"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if line.strip().lower() == 'date':
            for j in range(i + 1, min(i + 6, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


def _extract_alameda_county_industries_date(text: str) -> Optional[str]:
    """Alameda County Industries - INV. DATE columnar MM/DD/YYYY"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if 'inv. date' in line.lower() or 'inv date' in line.lower():
            for j in range(i + 1, min(i + 6, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


def _extract_minnkota_recycling_date(text: str) -> Optional[str]:
    """Minnkota Recycling - Invoice Date columnar M/DD/YYYY"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if 'invoice date' in line.lower():
            for j in range(i + 1, min(i + 5, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


def _extract_ctl_3r_technology_date(text: str) -> Optional[str]:
    """CTL 3R Technology - DATE columnar MM/DD/YYYY"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if line.strip().upper() == 'DATE':
            for j in range(i + 1, min(i + 5, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


def _extract_city_of_grand_junction_date(text: str) -> Optional[str]:
    """City of Grand Junction - service date after Trash Service label"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if 'trash service' in line.lower():
            for j in range(i + 1, min(i + 5, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


def _extract_city_of_del_rio_date(text: str) -> Optional[str]:
    """City of Del Rio - Due Date columnar MM/DD/YYYY"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if 'due date' in line.lower():
            for j in range(i + 1, min(i + 5, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


def _extract_a_and_i_pallets_date(text: str) -> Optional[str]:
    """A&I Pallets - DATE columnar MM/DD/YYYY"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if line.strip().upper() == 'DATE':
            for j in range(i + 1, min(i + 8, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


def _extract_chris_rizzo_trucking_date(text: str) -> Optional[str]:
    """Chris Rizzo Trucking - received on M/D/YYYY (TrashBilling)"""
    text = _normalize_text(text)
    m = re.search(r'received\s+on\s+(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})', text, re.IGNORECASE)
    if m:
        return _parse_date_match(m, 'MDY')
    return None


# --- Tranche 69 ---
def _extract_wrights_environmental_date(text: str) -> Optional[str]:
    """Wright's Environmental - TrashBilling Weekday Mon DD, YYYY format"""
    text = _normalize_text(text)
    m = re.search(r'(?:Mon|Tue|Wed|Thu|Fri|Sat|Sun)\s+([A-Za-z]{3})\s+(\d{1,2}),?\s+(\d{4})', text)
    if m:
        month = MONTH_MAP.get(m.group(1).lower()[:3])
        if month:
            day, year = int(m.group(2)), int(m.group(3))
            if _validate_date(month, day, year):
                return _format_date(month, day, year)
    return None


def _extract_timmons_waste_service_date(text: str) -> Optional[str]:
    """Timmons Waste Service - Invoice Date columnar MM/DD/YYYY"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if 'invoice date' in line.lower():
            for j in range(i + 1, min(i + 5, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


def _extract_city_of_dumas_date(text: str) -> Optional[str]:
    """City of Dumas - Bill Date columnar M/D/YYYY"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if 'bill date' in line.lower():
            for j in range(i + 1, min(i + 5, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


def _extract_coles_county_sanitation_date(text: str) -> Optional[str]:
    """Coles County Sanitation - TrashBilling Weekday Mon DD, YYYY format"""
    text = _normalize_text(text)
    m = re.search(r'(?:Mon|Tue|Wed|Thu|Fri|Sat|Sun)\s+([A-Za-z]{3})\s+(\d{1,2}),?\s+(\d{4})', text)
    if m:
        month = MONTH_MAP.get(m.group(1).lower()[:3])
        if month:
            day, year = int(m.group(2)), int(m.group(3))
            if _validate_date(month, day, year):
                return _format_date(month, day, year)
    return None


def _extract_mountain_disposal_inc_date(text: str) -> Optional[str]:
    """Mountain Disposal Inc - TrashBilling Weekday Mon DD, YYYY format"""
    text = _normalize_text(text)
    m = re.search(r'(?:Mon|Tue|Wed|Thu|Fri|Sat|Sun)\s+([A-Za-z]{3})\s+(\d{1,2}),?\s+(\d{4})', text)
    if m:
        month = MONTH_MAP.get(m.group(1).lower()[:3])
        if month:
            day, year = int(m.group(2)), int(m.group(3))
            if _validate_date(month, day, year):
                return _format_date(month, day, year)
    return None


def _extract_panola_county_solid_waste_date(text: str) -> Optional[str]:
    """Panola County Solid Waste - DUE DATE MM/DD/YY inline"""
    text = _normalize_text(text)
    m = re.search(r'(\d{1,2})[/\-](\d{1,2})[/\-](\d{2})\s*\.', text)
    if m:
        return _parse_date_match(m, 'MDY')
    return None


def _extract_daynes_waste_disposal_date(text: str) -> Optional[str]:
    """Dayne's Waste Disposal - Date columnar M/DD/YYYY"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if line.strip().lower() == 'date':
            for j in range(i + 1, min(i + 5, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


def _extract_pratt_recycling_date(text: str) -> Optional[str]:
    """Pratt Recycling - DATE columnar Mon-DD-YY or Del.Date columnar MM/DD/YYYY"""
    text = _normalize_text(text)
    lines = text.split('\n')
    # Try DATE header with Mon-DD-YY format
    for i, line in enumerate(lines):
        if line.strip().upper() == 'DATE':
            for j in range(i + 1, min(i + 6, len(lines))):
                m = re.match(r'^\s*([A-Za-z]{3})-(\d{2})-(\d{2})\s*$', lines[j].strip())
                if m:
                    month = MONTH_MAP.get(m.group(1).lower()[:3])
                    if month:
                        day, year = int(m.group(2)), int(m.group(3))
                        if year < 50:
                            year += 2000
                        else:
                            year += 1900
                        if _validate_date(month, day, year):
                            return _format_date(month, day, year)
    # Try Del.Date header with MM/DD/YYYY format
    for i, line in enumerate(lines):
        if 'del.date' in line.lower():
            for j in range(i + 1, min(i + 30, len(lines))):
                m = re.search(r'(\d{1,2})[/\-](\d{1,2})[/\-](\d{4})', lines[j])
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


def _extract_city_of_vinita_date(text: str) -> Optional[str]:
    """City of Vinita - Transaction Time M/D/YYYY inline"""
    text = _normalize_text(text)
    m = re.search(r'(\d{1,2})[/\-](\d{1,2})[/\-](\d{4})\s+\d{1,2}:\d{2}:\d{2}\s+[AP]M', text)
    if m:
        return _parse_date_match(m, 'MDY')
    return None


def _extract_clackamas_garbage_date(text: str) -> Optional[str]:
    """Clackamas Garbage - Bill Date Month DD, YYYY inline"""
    text = _normalize_text(text)
    m = re.search(r'Bill\s+Date\s+([A-Za-z]+)\s+(\d{1,2}),?\s+(\d{4})', text, re.IGNORECASE)
    if m:
        month = MONTH_MAP.get(m.group(1).lower()[:3])
        if month:
            day, year = int(m.group(2)), int(m.group(3))
            if _validate_date(month, day, year):
                return _format_date(month, day, year)
    return None


def _extract_delta_garbage_service_date(text: str) -> Optional[str]:
    """Delta Garbage Service - Date columnar M/D/YYYY"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if line.strip().lower() == 'date':
            for j in range(i + 1, min(i + 5, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


def _extract_roseburg_disposal_date(text: str) -> Optional[str]:
    """Roseburg Disposal - DATE columnar MM/DD/YYYY"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if line.strip().upper() == 'DATE':
            for j in range(i + 1, min(i + 20, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s+', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


# --- Tranche 70 ---
def _extract_waste_removal_and_recycling_date(text: str) -> Optional[str]:
    """Waste Removal & Recycling - Date columnar M/DD/YYYY"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if line.strip().lower() == 'date':
            for j in range(i + 1, min(i + 5, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


def _extract_westside_disposal_date(text: str) -> Optional[str]:
    """Westside Disposal - Payment date columnar MM/DD/YYYY"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if 'payment date' in line.lower():
            for j in range(i + 1, min(i + 6, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


def _extract_palm_springs_disposal_date(text: str) -> Optional[str]:
    """Palm Springs Disposal - BILLING PERIOD columnar Month YYYY"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if 'billing period' in line.lower():
            for j in range(i + 1, min(i + 5, len(lines))):
                m = re.match(r'^\s*([A-Za-z]+)\s+(\d{4})\s*$', lines[j].strip())
                if m:
                    month = MONTH_MAP.get(m.group(1).lower()[:3])
                    if month:
                        year = int(m.group(2))
                        return _format_date(month, 1, year)
    return None


def _extract_tacoma_public_utilities_date(text: str) -> Optional[str]:
    """Tacoma Public Utilities - Date: MM/DD/YYYY inline"""
    text = _normalize_text(text)
    m = re.search(r'Date:\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})', text, re.IGNORECASE)
    if m:
        return _parse_date_match(m, 'MDY')
    return None


def _extract_south_plains_waste_date(text: str) -> Optional[str]:
    """South Plains Waste - DATE columnar M/DD/YYYY"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if line.strip().upper() == 'DATE':
            for j in range(i + 1, min(i + 5, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


def _extract_earthsavers_date(text: str) -> Optional[str]:
    """EarthSavers - Invoice Date: columnar Month D, YYYY"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if 'invoice date' in line.lower():
            for j in range(i + 1, min(i + 5, len(lines))):
                m = re.match(r'^\s*([A-Za-z]+)\s+(\d{1,2}),?\s+(\d{4})\s*$', lines[j].strip())
                if m:
                    month = MONTH_MAP.get(m.group(1).lower()[:3])
                    if month:
                        day, year = int(m.group(2)), int(m.group(3))
                        if _validate_date(month, day, year):
                            return _format_date(month, day, year)
    return None


def _extract_brannon_industrial_date(text: str) -> Optional[str]:
    """Brannon Industrial - DATE columnar Mon DD, YYYY"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if line.strip().upper() == 'DATE':
            for j in range(i + 1, min(i + 6, len(lines))):
                m = re.match(r'^\s*([A-Za-z]{3})\s+(\d{1,2}),?\s+(\d{4})\s*$', lines[j].strip())
                if m:
                    month = MONTH_MAP.get(m.group(1).lower()[:3])
                    if month:
                        day, year = int(m.group(2)), int(m.group(3))
                        if _validate_date(month, day, year):
                            return _format_date(month, day, year)
    return None


def _extract_centre_water_works_date(text: str) -> Optional[str]:
    """Centre Water Works - BILL DATE columnar MM/DD/YY"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if 'bill date' in line.lower():
            for j in range(i + 1, min(i + 5, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


def _extract_scraps_compost_date(text: str) -> Optional[str]:
    """Scraps Compost - Date paid Month DD, YYYY inline"""
    text = _normalize_text(text)
    m = re.search(r'Date\s+paid\s+([A-Za-z]+)\s+(\d{1,2}),?\s+(\d{4})', text, re.IGNORECASE)
    if m:
        month = MONTH_MAP.get(m.group(1).lower()[:3])
        if month:
            day, year = int(m.group(2)), int(m.group(3))
            if _validate_date(month, day, year):
                return _format_date(month, day, year)
    return None


def _extract_niese_hauling_date(text: str) -> Optional[str]:
    """Niese Hauling - Invoice date: MM/DD/YYYY inline"""
    text = _normalize_text(text)
    m = re.search(r'Invoice\s+date:\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})', text, re.IGNORECASE)
    if m:
        return _parse_date_match(m, 'MDY')
    return None


def _extract_dc_metals_date(text: str) -> Optional[str]:
    """DC Metals - Date columnar M/D/YYYY"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if line.strip().lower() == 'date':
            for j in range(i + 1, min(i + 5, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


def _extract_empire_disposal_date(text: str) -> Optional[str]:
    """Empire Disposal - STATEMENT DATE columnar MM/DD/YYYY"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if 'statement date' in line.lower():
            for j in range(i + 1, min(i + 5, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


# --- Tranche 71 ---
def _extract_city_of_cartersville_date(text: str) -> Optional[str]:
    """City of Cartersville - Billing Date columnar Mon D, YYYY"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if 'billing date' in line.lower():
            for j in range(i + 1, min(i + 5, len(lines))):
                m = re.match(r'^\s*([A-Za-z]{3})\s+(\d{1,2}),?\s+(\d{4})\s*$', lines[j].strip())
                if m:
                    month = MONTH_MAP.get(m.group(1).lower()[:3])
                    if month:
                        day, year = int(m.group(2)), int(m.group(3))
                        if _validate_date(month, day, year):
                            return _format_date(month, day, year)
    return None


def _extract_city_of_gainesville_tx_date(text: str) -> Optional[str]:
    """City of Gainesville TX - BILL DATE columnar MM/DD/YYYY"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if 'bill date' in line.lower():
            for j in range(i + 1, min(i + 10, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


def _extract_city_of_fort_smith_date(text: str) -> Optional[str]:
    """City of Fort Smith - Due Date columnar MM/DD/YYYY"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if 'due date' in line.lower():
            for j in range(i + 1, min(i + 5, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


def _extract_lorens_sanitation_date(text: str) -> Optional[str]:
    """Loren's Sanitation - CLOSING DATE columnar M/DD/YY"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if 'closing date' in line.lower():
            for j in range(i + 1, min(i + 5, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


def _extract_weiner_iron_and_metal_date(text: str) -> Optional[str]:
    """Weiner Iron & Metal - Invoice Date: M/D/YYYY inline"""
    text = _normalize_text(text)
    m = re.search(r'Invoice\s+Date:\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})', text, re.IGNORECASE)
    if m:
        return _parse_date_match(m, 'MDY')
    return None


def _extract_besttrash_date(text: str) -> Optional[str]:
    """BestTrash - DATE columnar Mon D, YYYY"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if line.strip().upper() == 'DATE':
            for j in range(i + 1, min(i + 5, len(lines))):
                m = re.match(r'^\s*([A-Za-z]{3})\s+(\d{1,2}),?\s+(\d{4})\s*$', lines[j].strip())
                if m:
                    month = MONTH_MAP.get(m.group(1).lower()[:3])
                    if month:
                        day, year = int(m.group(2)), int(m.group(3))
                        if _validate_date(month, day, year):
                            return _format_date(month, day, year)
    return None


def _extract_c_and_c_disposal_date(text: str) -> Optional[str]:
    """C&C Disposal - INVOICE DATE columnar MM/DD/YYYY"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if 'invoice date' in line.lower():
            for j in range(i + 1, min(i + 5, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{4})', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


def _extract_chum_refuse_date(text: str) -> Optional[str]:
    """Chum Refuse - Invoice Date columnar MM/DD/YYYY"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if 'invoice date' in line.lower():
            for j in range(i + 1, min(i + 8, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


def _extract_sustainable_environmental_management_date(text: str) -> Optional[str]:
    """Sustainable Environmental Management - DATE: columnar M/DD/YYYY"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if line.strip().upper().startswith('DATE:'):
            for j in range(i + 1, min(i + 5, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


def _extract_main_street_fibers_date(text: str) -> Optional[str]:
    """Main Street Fibers - Invoice Date columnar MM/DD/YY"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if 'invoice date' in line.lower():
            for j in range(i + 1, min(i + 5, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


def _extract_city_of_lompoc_date(text: str) -> Optional[str]:
    """City of Lompoc - Due Date columnar MM/DD/YYYY"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if 'due date' in line.lower():
            for j in range(i + 1, min(i + 5, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{4})', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


def _extract_emery_county_sanitation_date(text: str) -> Optional[str]:
    """Emery County Sanitation - Statement Date: Mon DD, YYYY inline"""
    text = _normalize_text(text)
    m = re.search(r'Statement\s+Date:\s*([A-Za-z]{3})\s+(\d{1,2}),?\s+(\d{4})', text, re.IGNORECASE)
    if m:
        month = MONTH_MAP.get(m.group(1).lower()[:3])
        if month:
            day, year = int(m.group(2)), int(m.group(3))
            if _validate_date(month, day, year):
                return _format_date(month, day, year)
    return None


# --- Tranche 72 ---
def _extract_elecke_date(text: str) -> Optional[str]:
    """Elecke - Date columnar MM/DD/YYYY"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if line.strip().lower() == 'date':
            for j in range(i + 1, min(i + 5, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


def _extract_amg_resources_date(text: str) -> Optional[str]:
    """AMG Resources - INVOICE DATE: MM/DD/YYYY inline"""
    text = _normalize_text(text)
    m = re.search(r'INVOICE\s+DATE:\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})', text, re.IGNORECASE)
    if m:
        return _parse_date_match(m, 'MDY')
    return None


def _extract_sunny_trash_hauling_date(text: str) -> Optional[str]:
    """Sunny Trash Hauling - INVOICE DATE columnar Mon DD, YYYY"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if 'invoice date' in line.lower():
            for j in range(i + 1, min(i + 5, len(lines))):
                m = re.match(r'^\s*([A-Za-z]{3})\s+(\d{1,2}),?\s+(\d{4})\s*$', lines[j].strip())
                if m:
                    month = MONTH_MAP.get(m.group(1).lower()[:3])
                    if month:
                        day, year = int(m.group(2)), int(m.group(3))
                        if _validate_date(month, day, year):
                            return _format_date(month, day, year)
    return None


def _extract_american_reclamation_date(text: str) -> Optional[str]:
    """American Reclamation - Invoice Date columnar M/D/YY"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if 'invoice date' in line.lower():
            for j in range(i + 1, min(i + 8, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


def _extract_msc_industries_date(text: str) -> Optional[str]:
    """MSC Industries - DATE reverse columnar MM/DD/YYYY"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if line.strip().upper() == 'DATE':
            for j in range(max(0, i - 5), i):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


def _extract_american_resource_management_date(text: str) -> Optional[str]:
    """American Resource Management - Date columnar M/D/YYYY"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if line.strip().lower() == 'date':
            for j in range(i + 1, min(i + 8, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


def _extract_irow_date(text: str) -> Optional[str]:
    """IROW - Invoice Date: columnar Mon DD, YYYY"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if 'invoice date' in line.lower():
            for j in range(i + 1, min(i + 6, len(lines))):
                m = re.match(r'^\s*([A-Za-z]{3})\s+(\d{1,2}),?\s+(\d{4})\s*$', lines[j].strip())
                if m:
                    month = MONTH_MAP.get(m.group(1).lower()[:3])
                    if month:
                        day, year = int(m.group(2)), int(m.group(3))
                        if _validate_date(month, day, year):
                            return _format_date(month, day, year)
    return None


def _extract_agri_cycle_date(text: str) -> Optional[str]:
    """Agri-Cycle - DATE columnar DD-Mon-YYYY"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if line.strip().upper() == 'DATE':
            for j in range(i + 1, min(i + 5, len(lines))):
                m = re.match(r'^\s*(\d{1,2})-([A-Za-z]{3})-(\d{4})\s*$', lines[j].strip())
                if m:
                    day = int(m.group(1))
                    month = MONTH_MAP.get(m.group(2).lower()[:3])
                    year = int(m.group(3))
                    if month and _validate_date(month, day, year):
                        return _format_date(month, day, year)
    return None


def _extract_friends_garbage_date(text: str) -> Optional[str]:
    """Friends Garbage - first transaction date MM/DD/YYYY"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if 'date description' in line.lower():
            for j in range(i + 1, min(i + 15, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{4})', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


def _extract_brandts_sanitary_date(text: str) -> Optional[str]:
    """Brandt's Sanitary - first transaction date MM/DD/YYYY"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if line.strip().upper() == 'DATE':
            for j in range(i + 1, min(i + 15, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{4})', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


def _extract_city_of_durant_date(text: str) -> Optional[str]:
    """City of Durant - Due Date columnar M/DD/YYYY"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if 'due date' in line.lower():
            for j in range(i + 1, min(i + 5, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


def _extract_watertown_iron_date(text: str) -> Optional[str]:
    """Watertown Iron - Inv Date: MM/DD/YYYY inline"""
    text = _normalize_text(text)
    m = re.search(r'Inv\s+Date:\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})', text, re.IGNORECASE)
    if m:
        return _parse_date_match(m, 'MDY')
    return None


# --- Tranche 73 ---

def _extract_top_dog_waste_date(text: str) -> Optional[str]:
    """Top Dog Waste - DATE columnar Mon DD, YYYY (NavuSoft, wide spacing)"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if line.strip().upper() == 'DATE':
            for j in range(i + 1, min(i + 12, len(lines))):
                m = re.match(r'^\s*([A-Za-z]{3})\s+(\d{1,2}),?\s*(\d{4})\s*$', lines[j].strip())
                if m:
                    month = MONTH_MAP.get(m.group(1).lower()[:3])
                    if month:
                        day, year = int(m.group(2)), int(m.group(3))
                        if _validate_date(month, day, year):
                            return _format_date(month, day, year)
    return None


def _extract_kurtzmans_sanitation_date(text: str) -> Optional[str]:
    """Kurtzman's Sanitation - Date columnar M/DD/YYYY"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if line.strip().lower() == 'date':
            for j in range(i + 1, min(i + 5, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


def _extract_central_valley_disposal_date(text: str) -> Optional[str]:
    """Central Valley Disposal - Date inline M/DD/YYYY"""
    text = _normalize_text(text)
    m = re.search(r'\bDate[:\s]+(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})', text, re.IGNORECASE)
    if m:
        return _parse_date_match(m, 'MDY')
    return None


def _extract_mulberry_ventures_date(text: str) -> Optional[str]:
    """Mulberry Ventures - DATE columnar M/DD/YYYY"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if line.strip().upper() == 'DATE':
            for j in range(i + 1, min(i + 5, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


def _extract_green_environmental_services_date(text: str) -> Optional[str]:
    """Green Environmental Services - DATE columnar MM/DD/YYYY (transaction date, wide spacing)"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if line.strip().upper() == 'DATE':
            for j in range(i + 1, min(i + 12, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


def _extract_federal_recycling_and_waste_solutions_date(text: str) -> Optional[str]:
    """Federal Recycling & Waste Solutions - DATE columnar MM/DD/YYYY"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if line.strip().upper() == 'DATE':
            for j in range(i + 1, min(i + 5, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


def _extract_old_west_disposal_date(text: str) -> Optional[str]:
    """Old West Disposal - DATE columnar MM/DD/YYYY"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if line.strip().upper() == 'DATE':
            for j in range(i + 1, min(i + 5, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


def _extract_city_of_colby_date(text: str) -> Optional[str]:
    """City of Colby - Billing Date columnar M/DD/YYYY"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if 'billing date' in line.lower():
            for j in range(i + 1, min(i + 5, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


def _extract_mavilyn_industries_date(text: str) -> Optional[str]:
    """Mavilyn Industries - DATE reverse columnar MM/DD/YYYY"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if line.strip().upper() == 'DATE':
            for j in range(max(0, i - 5), i):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


def _extract_j_and_s_trash_collection_date(text: str) -> Optional[str]:
    """J & S Trash Collection - TrashBilling Weekday Mon DD, YYYY"""
    text = _normalize_text(text)
    m = re.search(r'(?:Mon|Tue|Wed|Thu|Fri|Sat|Sun)\s+([A-Za-z]{3})\s+(\d{1,2}),?\s*(\d{4})', text)
    if m:
        month = MONTH_MAP.get(m.group(1).lower()[:3])
        if month:
            day, year = int(m.group(2)), int(m.group(3))
            if _validate_date(month, day, year):
                return _format_date(month, day, year)
    return None


def _extract_commonwealth_waste_solutions_date(text: str) -> Optional[str]:
    """Commonwealth Waste Solutions - Date columnar M/DD/YYYY"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if line.strip().lower() == 'date':
            for j in range(i + 1, min(i + 5, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


def _extract_canusa_hershman_date(text: str) -> Optional[str]:
    """Canusa Hershman - Mon D, YYYY after invoice number"""
    text = _normalize_text(text)
    m = re.search(r'([A-Za-z]{3})\s+(\d{1,2}),?\s*(\d{4})', text)
    if m:
        month = MONTH_MAP.get(m.group(1).lower()[:3])
        if month:
            day, year = int(m.group(2)), int(m.group(3))
            if _validate_date(month, day, year):
                return _format_date(month, day, year)
    return None


# --- Tranche 74 ---

def _extract_kings_roll_off_date(text: str) -> Optional[str]:
    """Kings Roll-Off - Invoice Date: M/D/YYYY inline"""
    text = _normalize_text(text)
    m = re.search(r'Invoice\s+Date:\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})', text, re.IGNORECASE)
    if m:
        return _parse_date_match(m, 'MDY')
    return None


def _extract_dallas_recycling_date(text: str) -> Optional[str]:
    """Dallas Recycling - DATE columnar MM/DD/YYYY"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if line.strip().upper() == 'DATE':
            for j in range(i + 1, min(i + 5, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


def _extract_cwsi_date(text: str) -> Optional[str]:
    """CWSI - Date: M/D/YY inline or standalone date"""
    text = _normalize_text(text)
    m = re.search(r'\bDate:\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})', text, re.IGNORECASE)
    if m:
        return _parse_date_match(m, 'MDY')
    # Try standalone date near start
    lines = text.split('\n')
    for line in lines[:10]:
        m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', line.strip())
        if m:
            return _parse_date_match(m, 'MDY')
    return None


def _extract_edge_waste_date(text: str) -> Optional[str]:
    """Edge Waste - TrashBilling Weekday Mon D, YYYY"""
    text = _normalize_text(text)
    m = re.search(r'(?:Mon|Tue|Wed|Thu|Fri|Sat|Sun)\s+([A-Za-z]{3})\s+(\d{1,2}),?\s*(\d{4})', text)
    if m:
        month = MONTH_MAP.get(m.group(1).lower()[:3])
        if month:
            day, year = int(m.group(2)), int(m.group(3))
            if _validate_date(month, day, year):
                return _format_date(month, day, year)
    return None


def _extract_wasteless_solutions_date(text: str) -> Optional[str]:
    """Wasteless Solutions - DATE columnar MM/DD/YYYY"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if line.strip().upper() == 'DATE':
            for j in range(i + 1, min(i + 5, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


def _extract_hometown_disposal_date(text: str) -> Optional[str]:
    """Hometown Disposal - DATE columnar MM/DD/YYYY (wide spacing)"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if line.strip().upper() == 'DATE':
            for j in range(i + 1, min(i + 8, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


def _extract_smoky_mountain_waste_date(text: str) -> Optional[str]:
    """Smoky Mountain Waste - Date columnar M/D/YYYY"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if line.strip().lower() == 'date':
            for j in range(i + 1, min(i + 5, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


def _extract_allied_recycling_date(text: str) -> Optional[str]:
    """Allied Recycling - Date columnar M/D/YYYY (wide spacing)"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if line.strip().lower() == 'date':
            for j in range(i + 1, min(i + 8, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


def _extract_enviromax_recycling_date(text: str) -> Optional[str]:
    """Enviromax Recycling - DATE columnar MM/DD/YYYY (wide spacing)"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if line.strip().upper() == 'DATE':
            for j in range(i + 1, min(i + 12, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


def _extract_city_of_kirkland_date(text: str) -> Optional[str]:
    """City of Kirkland - Bill Date columnar MM/DD/YYYY"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if 'bill date' in line.lower():
            for j in range(i + 1, min(i + 5, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


def _extract_loren_fischer_disposal_date(text: str) -> Optional[str]:
    """Loren Fischer Disposal - TrashBilling Weekday Mon D, YYYY"""
    text = _normalize_text(text)
    m = re.search(r'(?:Mon|Tue|Wed|Thu|Fri|Sat|Sun)\s+([A-Za-z]{3})\s+(\d{1,2}),?\s*(\d{4})', text)
    if m:
        month = MONTH_MAP.get(m.group(1).lower()[:3])
        if month:
            day, year = int(m.group(2)), int(m.group(3))
            if _validate_date(month, day, year):
                return _format_date(month, day, year)
    return None


def _extract_pluffmud_recycling_date(text: str) -> Optional[str]:
    """Pluffmud Recycling - INVOICE header then M/D/YYYY on next line"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if line.strip().upper() == 'INVOICE':
            for j in range(i + 1, min(i + 5, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


# --- Tranche 75 ---

def _extract_yreka_transfer_date(text: str) -> Optional[str]:
    """Yreka Transfer - Transaction Date: MM/DD/YYYY columnar"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if 'transaction date' in line.lower():
            for j in range(i + 1, min(i + 5, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


def _extract_monterey_city_disposal_date(text: str) -> Optional[str]:
    """Monterey City Disposal - INVOICE DATE columnar M/DD/YYYY"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if 'invoice date' in line.lower():
            for j in range(i + 1, min(i + 5, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


def _extract_break_it_down_date(text: str) -> Optional[str]:
    """Break It Down - Invoice date: MM/DD/YYYY inline"""
    text = _normalize_text(text)
    m = re.search(r'Invoice\s+date:\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})', text, re.IGNORECASE)
    if m:
        return _parse_date_match(m, 'MDY')
    return None


def _extract_north_lincoln_sanitary_date(text: str) -> Optional[str]:
    """North Lincoln Sanitary - Bill Date columnar Month DD, YYYY"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if 'bill date' in line.lower():
            for j in range(i + 1, min(i + 5, len(lines))):
                m = re.match(r'^\s*([A-Za-z]+)\s+(\d{1,2}),?\s*(\d{4})\s*$', lines[j].strip())
                if m:
                    month = MONTH_MAP.get(m.group(1).lower()[:3])
                    if month:
                        day, year = int(m.group(2)), int(m.group(3))
                        if _validate_date(month, day, year):
                            return _format_date(month, day, year)
    return None


def _extract_ace_sanitation_service_date(text: str) -> Optional[str]:
    """Ace Sanitation Service - received on M/DD/YYYY (TrashBilling receipt)"""
    text = _normalize_text(text)
    m = re.search(r'received\s+on\s+(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})', text, re.IGNORECASE)
    if m:
        return _parse_date_match(m, 'MDY')
    return None


def _extract_all_states_rentals_date(text: str) -> Optional[str]:
    """All States Rentals - Invoice Date: M/D/YYYY columnar"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if 'invoice date' in line.lower():
            for j in range(i + 1, min(i + 5, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


def _extract_breezy_hollow_date(text: str) -> Optional[str]:
    """Breezy Hollow - DATE MM-D-YY inline"""
    text = _normalize_text(text)
    m = re.search(r'\bDATE\s+(\d{1,2})-(\d{1,2})-(\d{2,4})', text, re.IGNORECASE)
    if m:
        return _parse_date_match(m, 'MDY')
    return None


def _extract_city_of_largo_date(text: str) -> Optional[str]:
    """City of Largo - Bill Date columnar MM/DD/YY"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if 'bill date' in line.lower():
            for j in range(i + 1, min(i + 5, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


def _extract_c_stoneham_date(text: str) -> Optional[str]:
    """C Stoneham - Invoice Date: Mon DD, YYYY inline"""
    text = _normalize_text(text)
    m = re.search(r'Invoice\s+Date:\s*([A-Za-z]{3})\s+(\d{1,2}),?\s*(\d{4})', text, re.IGNORECASE)
    if m:
        month = MONTH_MAP.get(m.group(1).lower()[:3])
        if month:
            day, year = int(m.group(2)), int(m.group(3))
            if _validate_date(month, day, year):
                return _format_date(month, day, year)
    return None


def _extract_georgetown_paper_stock_date(text: str) -> Optional[str]:
    """Georgetown Paper Stock - DATE columnar MM/DD/YYYY"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if line.strip().upper() == 'DATE':
            for j in range(i + 1, min(i + 5, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


def _extract_malcom_enterprises_date(text: str) -> Optional[str]:
    """Malcom Enterprises - Weekday Mon DD, YYYY format"""
    text = _normalize_text(text)
    m = re.search(r'(?:Mon|Tue|Wed|Thu|Fri|Sat|Sun)\s+([A-Za-z]{3})\s+(\d{1,2}),?\s*(\d{4})', text)
    if m:
        month = MONTH_MAP.get(m.group(1).lower()[:3])
        if month:
            day, year = int(m.group(2)), int(m.group(3))
            if _validate_date(month, day, year):
                return _format_date(month, day, year)
    return None


def _extract_reddy_rentals_date(text: str) -> Optional[str]:
    """Reddy Rentals - Date columnar MM/DD/YYYY"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if line.strip().lower() == 'date':
            for j in range(i + 1, min(i + 5, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


# --- Tranche 76 ---

def _extract_city_of_tullahoma_date(text: str) -> Optional[str]:
    """City of Tullahoma - Statement Date columnar MM/DD/YYYY"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if 'statement date' in line.lower():
            for j in range(i + 1, min(i + 5, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


def _extract_davis_disposal_date(text: str) -> Optional[str]:
    """Davis Disposal - Invoice date: columnar MM/DD/YYYY"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if 'invoice date' in line.lower():
            for j in range(i + 1, min(i + 8, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


def _extract_crown_waste_and_recycling_date(text: str) -> Optional[str]:
    """Crown Waste & Recycling - Date MM/DD/YY inline"""
    text = _normalize_text(text)
    m = re.search(r'\bDate\s+(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})', text, re.IGNORECASE)
    if m:
        return _parse_date_match(m, 'MDY')
    return None


def _extract_standing_rock_sanitation_date(text: str) -> Optional[str]:
    """Standing Rock Sanitation - DATE columnar M/DD/YYYY (wide)"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if line.strip().upper() == 'DATE':
            for j in range(i + 1, min(i + 10, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


def _extract_sos_waste_disposal_date(text: str) -> Optional[str]:
    """SOS Waste Disposal - Invoice date: MM/DD/YYYY inline"""
    text = _normalize_text(text)
    m = re.search(r'Invoice\s+date:\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})', text, re.IGNORECASE)
    if m:
        return _parse_date_match(m, 'MDY')
    return None


def _extract_city_and_lakes_disposal_date(text: str) -> Optional[str]:
    """City & Lakes Disposal - INV DATE columnar MM/DD/YY"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if 'inv date' in line.lower():
            for j in range(i + 1, min(i + 5, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


def _extract_adams_disposal_date(text: str) -> Optional[str]:
    """Adam's Disposal - Issued Date: columnar Mon D, YYYY"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if 'issued date' in line.lower():
            for j in range(i + 1, min(i + 8, len(lines))):
                m = re.match(r'^\s*([A-Za-z]{3})\s+(\d{1,2}),?\s*(\d{4})\s*$', lines[j].strip())
                if m:
                    month = MONTH_MAP.get(m.group(1).lower()[:3])
                    if month:
                        day, year = int(m.group(2)), int(m.group(3))
                        if _validate_date(month, day, year):
                            return _format_date(month, day, year)
    return None


def _extract_golden_eagle_services_date(text: str) -> Optional[str]:
    """Golden Eagle Services - Invoice Date columnar MM/DD/YYYY"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if 'invoice date' in line.lower():
            for j in range(i + 1, min(i + 5, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


def _extract_hamilton_recycling_disposal_date(text: str) -> Optional[str]:
    """Hamilton Recycling Disposal - TrashBilling Weekday Mon DD, YYYY"""
    text = _normalize_text(text)
    m = re.search(r'(?:Mon|Tue|Wed|Thu|Fri|Sat|Sun)\s+([A-Za-z]{3})\s+(\d{1,2}),?\s*(\d{4})', text)
    if m:
        month = MONTH_MAP.get(m.group(1).lower()[:3])
        if month:
            day, year = int(m.group(2)), int(m.group(3))
            if _validate_date(month, day, year):
                return _format_date(month, day, year)
    return None


def _extract_maxshred_date(text: str) -> Optional[str]:
    """MaxShred - Invoice Date: MM/DD/YYYY inline"""
    text = _normalize_text(text)
    m = re.search(r'Invoice\s+Date:\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})', text, re.IGNORECASE)
    if m:
        return _parse_date_match(m, 'MDY')
    return None


def _extract_d_and_d_refuse_date(text: str) -> Optional[str]:
    """D & D Refuse - Date columnar MM/DD/YYYY (wide)"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if line.strip().lower() == 'date':
            for j in range(i + 1, min(i + 10, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


def _extract_big_river_disposal_date(text: str) -> Optional[str]:
    """Big River Disposal - received on M/D/YYYY (TrashBilling receipt)"""
    text = _normalize_text(text)
    m = re.search(r'received\s+on\s+(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})', text, re.IGNORECASE)
    if m:
        return _parse_date_match(m, 'MDY')
    return None


# --- Tranche 77 ---

def _extract_a1_little_john_date(text: str) -> Optional[str]:
    """A-1 Little John - DATE columnar MM/DD/YYYY"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if line.strip().upper() == 'DATE':
            for j in range(i + 1, min(i + 8, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


def _extract_edward_arnold_scrap_processors_date(text: str) -> Optional[str]:
    """Edward Arnold Scrap Processors - DATE columnar M/D/YYYY"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if line.strip().upper() == 'DATE':
            for j in range(i + 1, min(i + 5, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


def _extract_parish_disposal_date(text: str) -> Optional[str]:
    """Parish Disposal - DATE columnar MM/DD/YYYY"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if line.strip().upper() == 'DATE':
            for j in range(i + 1, min(i + 8, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


def _extract_ads_solid_waste_date(text: str) -> Optional[str]:
    """ADS Solid Waste - Invoice Date: columnar MM/DD/YYYY"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if 'invoice date' in line.lower():
            for j in range(i + 1, min(i + 8, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


def _extract_wft_waste_date(text: str) -> Optional[str]:
    """WFT Waste - DATE columnar M/D/YY"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if line.strip().upper() == 'DATE':
            for j in range(i + 1, min(i + 5, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


def _extract_kuerths_disposal_date(text: str) -> Optional[str]:
    """Kuerth's Disposal - Date columnar MM/DD/YYYY"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if line.strip().lower() == 'date':
            for j in range(i + 1, min(i + 5, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


def _extract_allen_disposal_date(text: str) -> Optional[str]:
    """Allen Disposal - received on M/D/YYYY (TrashBilling receipt)"""
    text = _normalize_text(text)
    m = re.search(r'received\s+on\s+(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})', text, re.IGNORECASE)
    if m:
        return _parse_date_match(m, 'MDY')
    return None


def _extract_ds_portable_toilets_date(text: str) -> Optional[str]:
    """D&S Portable Toilets - Date columnar Mon DD, YYYY"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if line.strip().lower() == 'date':
            for j in range(i + 1, min(i + 8, len(lines))):
                m = re.match(r'^\s*([A-Za-z]{3})\s+(\d{1,2}),?\s*(\d{4})\s*$', lines[j].strip())
                if m:
                    month = MONTH_MAP.get(m.group(1).lower()[:3])
                    if month:
                        day, year = int(m.group(2)), int(m.group(3))
                        if _validate_date(month, day, year):
                            return _format_date(month, day, year)
    return None


def _extract_georgia_waste_systems_date(text: str) -> Optional[str]:
    """Georgia Waste Systems - Invoice Date: columnar MM/DD/YYYY"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if 'invoice date' in line.lower():
            for j in range(i + 1, min(i + 8, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


def _extract_westside_waste_management_date(text: str) -> Optional[str]:
    """Westside Waste Management - Invoice Date: MM/DD/YYYY inline"""
    text = _normalize_text(text)
    m = re.search(r'Invoice\s+Date:\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})', text, re.IGNORECASE)
    if m:
        return _parse_date_match(m, 'MDY')
    return None


def _extract_j_and_jay_services_date(text: str) -> Optional[str]:
    """J&Jay Services - Issued Date: columnar Mon DD, YYYY"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if 'issued date' in line.lower():
            for j in range(i + 1, min(i + 8, len(lines))):
                m = re.match(r'^\s*([A-Za-z]{3})\s+(\d{1,2}),?\s*(\d{4})\s*$', lines[j].strip())
                if m:
                    month = MONTH_MAP.get(m.group(1).lower()[:3])
                    if month:
                        day, year = int(m.group(2)), int(m.group(3))
                        if _validate_date(month, day, year):
                            return _format_date(month, day, year)
    return None


def _extract_richland_county_landfill_date(text: str) -> Optional[str]:
    """Richland County Landfill - Invoice Date columnar Mon DD, YYYY"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if 'invoice date' in line.lower():
            for j in range(i + 1, min(i + 8, len(lines))):
                m = re.match(r'^\s*([A-Za-z]{3})\s+(\d{1,2}),?\s*(\d{4})\s*$', lines[j].strip())
                if m:
                    month = MONTH_MAP.get(m.group(1).lower()[:3])
                    if month:
                        day, year = int(m.group(2)), int(m.group(3))
                        if _validate_date(month, day, year):
                            return _format_date(month, day, year)
    return None


# --- Tranche 78 ---

def _extract_less_sanitation_date(text: str) -> Optional[str]:
    """Les's Sanitation - INV DATE columnar MM/DD/YY"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if 'inv date' in line.lower():
            for j in range(i + 1, min(i + 5, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


def _extract_city_of_las_cruces_date(text: str) -> Optional[str]:
    """City of Las Cruces - Billing Date columnar M/DD/YYYY"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if 'billing' in line.lower():
            for j in range(i + 1, min(i + 8, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


def _extract_southern_oregon_sanitation_date(text: str) -> Optional[str]:
    """Southern Oregon Sanitation - Statement: MM/DD/YYYY inline or Bill Date columnar"""
    text = _normalize_text(text)
    # Try Statement: inline first
    m = re.search(r'Statement:\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})', text, re.IGNORECASE)
    if m:
        return _parse_date_match(m, 'MDY')
    # Fall back to Bill Date columnar
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if 'bill date' in line.lower():
            for j in range(i + 1, min(i + 5, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


def _extract_texas_dumpsters_date(text: str) -> Optional[str]:
    """Texas Dumpsters - Invoice Date columnar MM/DD/YYYY"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if 'invoice date' in line.lower():
            for j in range(i + 1, min(i + 8, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


def _extract_city_of_winfield_date(text: str) -> Optional[str]:
    """City of Winfield - BILLING DATE columnar M/DD/YYYY"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if 'billing date' in line.lower():
            for j in range(i + 1, min(i + 5, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


def _extract_city_of_emporia_date(text: str) -> Optional[str]:
    """City of Emporia - BILLING DATE columnar MM/DD/YYYY"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if 'billing date' in line.lower():
            for j in range(i + 1, min(i + 8, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


def _extract_vanderpoel_disposal_date(text: str) -> Optional[str]:
    """Vanderpoel Disposal - Payment date columnar MM/DD/YYYY"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if 'payment date' in line.lower():
            for j in range(i + 1, min(i + 8, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


def _extract_mackenzie_disposal_date(text: str) -> Optional[str]:
    """Mackenzie Disposal - INVOICE DATE reverse columnar MM/DD/YY"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if 'invoice date' in line.lower():
            for j in range(max(0, i - 5), i):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


def _extract_community_sanitation_date(text: str) -> Optional[str]:
    """Community Sanitation - DATE: M/DD/YYYY inline"""
    text = _normalize_text(text)
    m = re.search(r'\bDATE:\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})', text, re.IGNORECASE)
    if m:
        return _parse_date_match(m, 'MDY')
    return None


def _extract_family_trash_service_date(text: str) -> Optional[str]:
    """Family Trash Service - DATE MM/DD/YYYY inline"""
    text = _normalize_text(text)
    m = re.search(r'\bDATE\s+(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})', text, re.IGNORECASE)
    if m:
        return _parse_date_match(m, 'MDY')
    return None


def _extract_cheyenne_board_of_public_utilities_date(text: str) -> Optional[str]:
    """Cheyenne Board of Public Utilities - BILL DATE columnar MM/DD/YYYY"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if 'bill date' in line.lower():
            for j in range(i + 1, min(i + 5, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


def _extract_accurate_paper_recycling_date(text: str) -> Optional[str]:
    """Accurate Paper Recycling - DATE columnar MM/DD/YYYY"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if line.strip().upper() == 'DATE':
            for j in range(i + 1, min(i + 5, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


# --- Tranche 79 ---

def _extract_wampler_services_date(text: str) -> Optional[str]:
    """Wampler Services - Invoice Date: columnar MM/DD/YYYY"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if 'invoice date' in line.lower():
            for j in range(i + 1, min(i + 5, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


def _extract_garretson_trash_service_date(text: str) -> Optional[str]:
    """Garretson Trash Service - received on M/DD/YYYY (TrashBilling)"""
    text = _normalize_text(text)
    m = re.search(r'received\s+on\s+(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})', text, re.IGNORECASE)
    if m:
        return _parse_date_match(m, 'MDY')
    return None


def _extract_armor_environmental_date(text: str) -> Optional[str]:
    """Armor Environmental - DATE MM/DD/YYYY inline"""
    text = _normalize_text(text)
    m = re.search(r'\bDATE\s+(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})', text, re.IGNORECASE)
    if m:
        return _parse_date_match(m, 'MDY')
    return None


def _extract_tims_trash_service_date(text: str) -> Optional[str]:
    """Tim's Trash Service - Payment date columnar YYYY-MM-DD"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if 'payment date' in line.lower():
            for j in range(i + 1, min(i + 5, len(lines))):
                m = re.match(r'^\s*(\d{4})-(\d{2})-(\d{2})\s*$', lines[j].strip())
                if m:
                    year, month, day = int(m.group(1)), int(m.group(2)), int(m.group(3))
                    if _validate_date(month, day, year):
                        return _format_date(month, day, year)
    return None


def _extract_humpty_dumpsters_date(text: str) -> Optional[str]:
    """Humpty Dumpsters - Payment date columnar MM/DD/YYYY"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if 'payment date' in line.lower():
            for j in range(i + 1, min(i + 8, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


def _extract_recycling_center_inc_date(text: str) -> Optional[str]:
    """Recycling Center Inc - Date: columnar MM/DD/YYYY"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if line.strip().lower() == 'date:':
            for j in range(i + 1, min(i + 5, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


def _extract_durflinger_disposal_service_date(text: str) -> Optional[str]:
    """Durflinger Disposal Service - DATE columnar M/DD/YYYY"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if line.strip().upper() == 'DATE':
            for j in range(i + 1, min(i + 5, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


def _extract_reliable_paper_recycling_date(text: str) -> Optional[str]:
    """Reliable Paper Recycling - first MM/DD/YYYY pattern in text"""
    text = _normalize_text(text)
    m = re.search(r'\b(\d{1,2})[/\-](\d{1,2})[/\-](\d{4})\b', text)
    if m:
        return _parse_date_match(m, 'MDY')
    return None


def _extract_darling_ingredients_date(text: str) -> Optional[str]:
    """Darling Ingredients - Date columnar MM/DD/YYYY (Invoice/Date split)"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if line.strip().lower() == 'date':
            for j in range(i + 1, min(i + 5, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


def _extract_city_of_laramie_date(text: str) -> Optional[str]:
    """City of Laramie - BILL DATE columnar M/DD/YYYY"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if 'bill date' in line.lower():
            for j in range(i + 1, min(i + 5, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


def _extract_city_of_rolla_date(text: str) -> Optional[str]:
    """City of Rolla - DATE columnar MM/DD/YYYY"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if line.strip().upper() == 'DATE':
            for j in range(i + 1, min(i + 5, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


def _extract_city_of_williston_date(text: str) -> Optional[str]:
    """City of Williston - Billed: MM/DD/YYYY inline"""
    text = _normalize_text(text)
    m = re.search(r'Billed:\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})', text, re.IGNORECASE)
    if m:
        return _parse_date_match(m, 'MDY')
    return None


# --- Tranche 80 ---

def _extract_murray_sanitation_date(text: str) -> Optional[str]:
    """Murray Sanitation - Invoice Date M/D/YYYY inline"""
    text = _normalize_text(text)
    m = re.search(r'Invoice\s+Date\s+(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})', text, re.IGNORECASE)
    if m:
        return _parse_date_match(m, 'MDY')
    return None


def _extract_nicholas_sanitation_date(text: str) -> Optional[str]:
    """Nicholas Sanitation - Invoice Date columnar MM/DD/YYYY"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if 'invoice date' in line.lower():
            for j in range(i + 1, min(i + 10, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


def _extract_h_and_h_sanitation_date(text: str) -> Optional[str]:
    """H & H Sanitation - DATE columnar MM/DD/YYYY"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if line.strip().upper() == 'DATE':
            for j in range(i + 1, min(i + 5, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


def _extract_key_disposal_and_recycling_date(text: str) -> Optional[str]:
    """Key Disposal & Recycling - INV DATE columnar MM/DD/YY"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if 'inv date' in line.lower():
            for j in range(i + 1, min(i + 5, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


def _extract_baker_sanitary_service_date(text: str) -> Optional[str]:
    """Baker Sanitary Service - DATE columnar M/D/YYYY (wide)"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if line.strip().upper() == 'DATE':
            for j in range(i + 1, min(i + 10, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


def _extract_tbs_waste_date(text: str) -> Optional[str]:
    """TBS Waste - INV DATE columnar MM/DD/YY"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if 'inv date' in line.lower():
            for j in range(i + 1, min(i + 5, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


def _extract_metalico_youngstown_date(text: str) -> Optional[str]:
    """Metalico Youngstown - Date:MM/DD/YY inline (no space)"""
    text = _normalize_text(text)
    m = re.search(r'\bDate:(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})', text, re.IGNORECASE)
    if m:
        return _parse_date_match(m, 'MDY')
    return None


def _extract_ely_disposal_service_date(text: str) -> Optional[str]:
    """Ely Disposal Service - Invoice Date: MM/DD/YYYY inline"""
    text = _normalize_text(text)
    m = re.search(r'Invoice\s+Date:\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})', text, re.IGNORECASE)
    if m:
        return _parse_date_match(m, 'MDY')
    return None


def _extract_town_of_lusk_date(text: str) -> Optional[str]:
    """Town of Lusk - DUE DATE columnar MM/DD/YYYY"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if 'due date' in line.lower() and 'amt' not in line.lower():
            for j in range(i + 1, min(i + 5, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


def _extract_ed_burris_disposal_date(text: str) -> Optional[str]:
    """Ed Burris Disposal - Date columnar MM/DD/YY"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if line.strip().lower() == 'date':
            for j in range(i + 1, min(i + 5, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


def _extract_cda_garbage_date(text: str) -> Optional[str]:
    """CDA Garbage - Invoice Date reverse columnar M/DD/YY"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if 'invoice date' in line.lower():
            for j in range(max(0, i - 12), i):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


def _extract_industrial_waste_and_salvage_date(text: str) -> Optional[str]:
    """Industrial Waste & Salvage - INVOICE DATE columnar M/DD/YYYY"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if 'invoice date' in line.lower():
            for j in range(i + 1, min(i + 5, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


# --- Tranche 81 ---

def _extract_dodds_trash_hauling_date(text: str) -> Optional[str]:
    """Dodd's Trash Hauling - look for any date in Month DD, YYYY format"""
    text = _normalize_text(text)
    m = re.search(r'(January|February|March|April|May|June|July|August|September|October|November|December)\s+(\d{1,2})(?:st|nd|rd|th)?,?\s*(\d{4})', text, re.IGNORECASE)
    if m:
        month = MONTH_MAP.get(m.group(1).lower()[:3])
        if month:
            day, year = int(m.group(2)), int(m.group(3))
            if _validate_date(month, day, year):
                return _format_date(month, day, year)
    return None


def _extract_jdog_junk_removal_date(text: str) -> Optional[str]:
    """JDog Junk Removal - Date columnar Weekday Mon DD, YYYY"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if line.strip().lower() == 'date':
            for j in range(i + 1, min(i + 5, len(lines))):
                m = re.match(r'^\s*(?:Mon|Tue|Wed|Thu|Fri|Sat|Sun)\s+([A-Za-z]{3})\s+(\d{1,2}),?\s*(\d{4})\s*$', lines[j].strip())
                if m:
                    month = MONTH_MAP.get(m.group(1).lower()[:3])
                    if month:
                        day, year = int(m.group(2)), int(m.group(3))
                        if _validate_date(month, day, year):
                            return _format_date(month, day, year)
    return None


def _extract_all_star_roll_off_date(text: str) -> Optional[str]:
    """All Star Roll-Off - Invoice Date columnar Mon DD, YYYY"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if 'invoice date' in line.lower():
            for j in range(i + 1, min(i + 5, len(lines))):
                m = re.match(r'^\s*([A-Za-z]{3})\s+(\d{1,2}),?\s*(\d{4})\s*$', lines[j].strip())
                if m:
                    month = MONTH_MAP.get(m.group(1).lower()[:3])
                    if month:
                        day, year = int(m.group(2)), int(m.group(3))
                        if _validate_date(month, day, year):
                            return _format_date(month, day, year)
    return None


def _extract_pratt_sanitation_date(text: str) -> Optional[str]:
    """Pratt Sanitation - TrashBilling 'received on M/D/YYYY'"""
    text = _normalize_text(text)
    m = re.search(r'received\s+on\s+(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})', text, re.IGNORECASE)
    if m:
        return _parse_date_match(m, 'MDY')
    return None


def _extract_advanced_document_solutions_date(text: str) -> Optional[str]:
    """Advanced Document Solutions - Invoice Print Date: columnar MM/DD/YYYY (wide)"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if 'invoice print date' in line.lower():
            for j in range(i + 1, min(i + 10, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


def _extract_city_of_hobbs_date(text: str) -> Optional[str]:
    """City of Hobbs - BILLING DATE: columnar M/DD/YYYY"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if 'billing date' in line.lower():
            for j in range(i + 1, min(i + 5, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


def _extract_jons_refuse_solutions_date(text: str) -> Optional[str]:
    """Jon's Refuse Solutions - DATE columnar MM/DD/YYYY"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if line.strip().upper() == 'DATE':
            for j in range(i + 1, min(i + 10, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


def _extract_bainbridge_disposal_date(text: str) -> Optional[str]:
    """Bainbridge Disposal - Transaction Date: columnar MM/DD/YYYY"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if 'transaction date' in line.lower():
            for j in range(i + 1, min(i + 5, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


def _extract_marcotte_disposal_date(text: str) -> Optional[str]:
    """Marcotte Disposal - TrashBilling Weekday Mon DD, YYYY before Invoice"""
    text = _normalize_text(text)
    m = re.search(r'(?:Mon|Tue|Wed|Thu|Fri|Sat|Sun)\s+([A-Za-z]{3})\s+(\d{1,2}),?\s*(\d{4})', text)
    if m:
        month = MONTH_MAP.get(m.group(1).lower()[:3])
        if month:
            day, year = int(m.group(2)), int(m.group(3))
            if _validate_date(month, day, year):
                return _format_date(month, day, year)
    return None


def _extract_city_of_devils_lake_date(text: str) -> Optional[str]:
    """City of Devils Lake - Billing Period End columnar MM/DD/YYYY"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if 'billing period end' in line.lower():
            for j in range(i + 1, min(i + 5, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


def _extract_hillsboro_garbage_disposal_date(text: str) -> Optional[str]:
    """Hillsboro Garbage Disposal - Statement Date columnar MM/DD/YYYY"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if 'statement date' in line.lower():
            for j in range(i + 1, min(i + 5, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


def _extract_r_and_r_recycling_inc_date(text: str) -> Optional[str]:
    """R&R Recycling Inc - Date columnar M/DD/YYYY"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if line.strip().lower() == 'date':
            for j in range(i + 1, min(i + 5, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


# --- Tranche 82 ---

def _extract_wemiga_waste_date(text: str) -> Optional[str]:
    """Wemiga Waste - Date columnar M/DD/YYYY"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if line.strip().lower() == 'date':
            for j in range(i + 1, min(i + 5, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


def _extract_sweetland_date(text: str) -> Optional[str]:
    """Sweetland - Date columnar MM/DD/YYYY"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if line.strip().lower() == 'date':
            for j in range(i + 1, min(i + 5, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


def _extract_city_of_socorro_date(text: str) -> Optional[str]:
    """City of Socorro - Bill Date columnar M/DD/YYYY (wide)"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if 'bill date' in line.lower():
            for j in range(i + 1, min(i + 10, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


def _extract_moon_companies_date(text: str) -> Optional[str]:
    """Moon Companies - DATE MM/DD/YYYY inline"""
    text = _normalize_text(text)
    m = re.search(r'\bDATE\s+(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})', text)
    if m:
        return _parse_date_match(m, 'MDY')
    return None


def _extract_iron_mountain_date(text: str) -> Optional[str]:
    """Iron Mountain - look for Invoice Date or first date in text"""
    text = _normalize_text(text)
    m = re.search(r'Invoice\s+Date:?\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})', text, re.IGNORECASE)
    if m:
        return _parse_date_match(m, 'MDY')
    # Fallback to first Month DD, YYYY pattern
    m = re.search(r'(January|February|March|April|May|June|July|August|September|October|November|December)\s+(\d{1,2}),?\s*(\d{4})', text, re.IGNORECASE)
    if m:
        month = MONTH_MAP.get(m.group(1).lower()[:3])
        if month:
            day, year = int(m.group(2)), int(m.group(3))
            if _validate_date(month, day, year):
                return _format_date(month, day, year)
    return None


def _extract_kaibab_band_date(text: str) -> Optional[str]:
    """Kaibab Band - PERIOD ENDING: MM/DD/YYYY inline"""
    text = _normalize_text(text)
    m = re.search(r'PERIOD\s+ENDING:\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})', text, re.IGNORECASE)
    if m:
        return _parse_date_match(m, 'MDY')
    return None


def _extract_town_of_wickenburg_date(text: str) -> Optional[str]:
    """Town of Wickenburg - Notice Date: M/DD/YYYY inline"""
    text = _normalize_text(text)
    m = re.search(r'Notice\s+Date:\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})', text, re.IGNORECASE)
    if m:
        return _parse_date_match(m, 'MDY')
    return None


def _extract_fisk_waste_removal_date(text: str) -> Optional[str]:
    """Fisk Waste Removal - BILL DATE columnar MM/DD/YY"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if 'bill date' in line.lower():
            for j in range(i + 1, min(i + 5, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


def _extract_town_of_dutch_john_date(text: str) -> Optional[str]:
    """Town of Dutch John - Date columnar M/D/YYYY"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if line.strip().lower() == 'date':
            for j in range(i + 1, min(i + 5, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


def _extract_waste_recycling_inc_date(text: str) -> Optional[str]:
    """Waste Recycling Inc - Date columnar M/D/YYYY"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if line.strip().lower() == 'date':
            for j in range(i + 1, min(i + 5, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


def _extract_ultimate_specialties_date(text: str) -> Optional[str]:
    """Ultimate Specialties - Date columnar MM/DD/YYYY"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if line.strip().lower() == 'date':
            for j in range(i + 1, min(i + 5, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


def _extract_bcda_the_trash_company_date(text: str) -> Optional[str]:
    """BCDA The Trash Company - TrashBilling Weekday Mon DD, YYYY"""
    text = _normalize_text(text)
    m = re.search(r'(?:Mon|Tue|Wed|Thu|Fri|Sat|Sun)\s+([A-Za-z]{3})\s+(\d{1,2}),?\s*(\d{4})', text)
    if m:
        month = MONTH_MAP.get(m.group(1).lower()[:3])
        if month:
            day, year = int(m.group(2)), int(m.group(3))
            if _validate_date(month, day, year):
                return _format_date(month, day, year)
    return None


# --- Tranche 83 ---

def _extract_mcs_midwest_date(text: str) -> Optional[str]:
    """MCS Midwest - Date columnar MM/DD/YYYY"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if line.strip().lower() == 'date':
            for j in range(i + 1, min(i + 5, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


def _extract_pleasanton_garbage_date(text: str) -> Optional[str]:
    """Pleasanton Garbage - INVOICE DATE columnar M/DD/YYYY"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if 'invoice date' in line.lower():
            for j in range(i + 1, min(i + 5, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


def _extract_mcallen_public_utility_date(text: str) -> Optional[str]:
    """McAllen Public Utility - Billing Date: M/DD/YYYY inline"""
    text = _normalize_text(text)
    m = re.search(r'Billing\s+Date:\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})', text, re.IGNORECASE)
    if m:
        return _parse_date_match(m, 'MDY')
    return None


def _extract_city_of_lamar_date(text: str) -> Optional[str]:
    """City of Lamar - Bill Date columnar MM/DD/YY"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if 'bill date' in line.lower():
            for j in range(i + 1, min(i + 5, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


def _extract_american_hauling_services_date(text: str) -> Optional[str]:
    """American Hauling Services - Invoice Date: Month DD, YYYY inline"""
    text = _normalize_text(text)
    m = re.search(r'Invoice\s+Date:\s*([A-Za-z]+)\s+(\d{1,2}),?\s*(\d{4})', text, re.IGNORECASE)
    if m:
        month = MONTH_MAP.get(m.group(1).lower()[:3])
        if month:
            day, year = int(m.group(2)), int(m.group(3))
            if _validate_date(month, day, year):
                return _format_date(month, day, year)
    return None


def _extract_andy_gump_date(text: str) -> Optional[str]:
    """Andy Gump - look for first date in MM/DD/YYYY format"""
    text = _normalize_text(text)
    m = re.search(r'\b(\d{1,2})[/\-](\d{1,2})[/\-](\d{4})\b', text)
    if m:
        return _parse_date_match(m, 'MDY')
    return None


def _extract_ctl_washington_date(text: str) -> Optional[str]:
    """CTL Washington - Invoice Date: MM/DD/YYYY inline"""
    text = _normalize_text(text)
    m = re.search(r'Invoice\s+Date:\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})', text, re.IGNORECASE)
    if m:
        return _parse_date_match(m, 'MDY')
    return None


def _extract_town_of_limon_date(text: str) -> Optional[str]:
    """Town of Limon - DUE DATE: columnar MM/DD/YY"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if 'due date' in line.lower():
            for j in range(i + 1, min(i + 10, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


def _extract_mosdell_sanitation_date(text: str) -> Optional[str]:
    """Mosdell Sanitation - TrashBilling Weekday Mon DD, YYYY"""
    text = _normalize_text(text)
    m = re.search(r'(?:Mon|Tue|Wed|Thu|Fri|Sat|Sun)\s+([A-Za-z]{3})\s+(\d{1,2}),?\s*(\d{4})', text)
    if m:
        month = MONTH_MAP.get(m.group(1).lower()[:3])
        if month:
            day, year = int(m.group(2)), int(m.group(3))
            if _validate_date(month, day, year):
                return _format_date(month, day, year)
    return None


def _extract_food_to_power_date(text: str) -> Optional[str]:
    """Food To Power - Date of issue Month DD, YYYY inline"""
    text = _normalize_text(text)
    m = re.search(r'Date\s+of\s+issue\s+([A-Za-z]+)\s+(\d{1,2}),?\s*(\d{4})', text, re.IGNORECASE)
    if m:
        month = MONTH_MAP.get(m.group(1).lower()[:3])
        if month:
            day, year = int(m.group(2)), int(m.group(3))
            if _validate_date(month, day, year):
                return _format_date(month, day, year)
    return None


def _extract_equipment_depot_northeast_date(text: str) -> Optional[str]:
    """Equipment Depot Northeast - Billing Date columnar M/D/YYYY"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if 'billing date' in line.lower():
            for j in range(i + 1, min(i + 5, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


def _extract_city_of_columbia_mo_date(text: str) -> Optional[str]:
    """City of Columbia MO - INVOICE DATE columnar M/DD/YYYY"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if 'invoice date' in line.lower():
            for j in range(i + 1, min(i + 5, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


# --- Tranche 84 ---

def _extract_southern_disposal_ar_date(text: str) -> Optional[str]:
    """Southern Disposal AR - Date columnar M/D/YYYY"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if line.strip().lower() == 'date':
            for j in range(i + 1, min(i + 5, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


def _extract_always_green_recycling_date(text: str) -> Optional[str]:
    """Always Green Recycling - Date columnar M/D/YYYY"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if line.strip().lower() == 'date':
            for j in range(i + 1, min(i + 5, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


def _extract_save_that_stuff_date(text: str) -> Optional[str]:
    """Save That Stuff - Invoice Date columnar M/DD/YY"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if 'invoice date' in line.lower():
            for j in range(i + 1, min(i + 5, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


def _extract_russell_county_sanitation_date(text: str) -> Optional[str]:
    """Russell County Sanitation - Billing Date: columnar MM/DD/YYYY (wide)"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if 'billing date' in line.lower():
            for j in range(i + 1, min(i + 12, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


def _extract_city_of_lewiston_date(text: str) -> Optional[str]:
    """City of Lewiston - Bill Date columnar MM/DD/YYYY"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if 'bill date' in line.lower():
            for j in range(i + 1, min(i + 5, len(lines))):
                m = re.search(r'(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})', lines[j])
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


def _extract_green_river_waste_date(text: str) -> Optional[str]:
    """Green River Waste - INV DATE columnar MM/DD/YY"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if 'inv date' in line.lower():
            for j in range(i + 1, min(i + 5, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


def _extract_roll_off_chick_date(text: str) -> Optional[str]:
    """Roll-Off Chick - Invoice Date: MM/D/YYYY inline"""
    text = _normalize_text(text)
    m = re.search(r'Invoice\s+Date:\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})', text, re.IGNORECASE)
    if m:
        return _parse_date_match(m, 'MDY')
    return None


def _extract_pinto_service_date(text: str) -> Optional[str]:
    """Pinto Service - Invoice Date columnar MM/DD/YY"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if 'invoice date' in line.lower():
            for j in range(i + 1, min(i + 5, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


def _extract_reed_maintenance_date(text: str) -> Optional[str]:
    """Reed Maintenance - Invoice Date: MM/DD/YYYY inline"""
    text = _normalize_text(text)
    m = re.search(r'Invoice\s+Date:\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})', text, re.IGNORECASE)
    if m:
        return _parse_date_match(m, 'MDY')
    return None


def _extract_tovar_equipment_date(text: str) -> Optional[str]:
    """Tovar Equipment - Invoice date columnar Mon DD, YYYY"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if 'invoice date' in line.lower():
            for j in range(i + 1, min(i + 10, len(lines))):
                m = re.match(r'^\s*([A-Za-z]{3})\s+(\d{1,2}),?\s*(\d{4})\s*$', lines[j].strip())
                if m:
                    month = MONTH_MAP.get(m.group(1).lower()[:3])
                    if month:
                        day, year = int(m.group(2)), int(m.group(3))
                        if _validate_date(month, day, year):
                            return _format_date(month, day, year)
    return None


def _extract_torrez_sanitation_date(text: str) -> Optional[str]:
    """Torrez Sanitation - TrashBilling Weekday Mon DD, YYYY"""
    text = _normalize_text(text)
    m = re.search(r'(?:Mon|Tue|Wed|Thu|Fri|Sat|Sun)\s+([A-Za-z]{3})\s+(\d{1,2}),?\s*(\d{4})', text)
    if m:
        month = MONTH_MAP.get(m.group(1).lower()[:3])
        if month:
            day, year = int(m.group(2)), int(m.group(3))
            if _validate_date(month, day, year):
                return _format_date(month, day, year)
    return None


def _extract_sids_garbage_date(text: str) -> Optional[str]:
    """Sid's Garbage - Invoice date: MM/DD/YYYY inline"""
    text = _normalize_text(text)
    m = re.search(r'Invoice\s+date:\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})', text, re.IGNORECASE)
    if m:
        return _parse_date_match(m, 'MDY')
    return None


# --- Tranche 85 ---

def _extract_aztec_waste_date(text: str) -> Optional[str]:
    """Aztec Waste - INV DATE columnar MM/DD/YY"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if 'inv date' in line.lower():
            for j in range(i + 1, min(i + 5, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


def _extract_pyles_demolition_recycling_date(text: str) -> Optional[str]:
    """Pyles Demolition Recycling - Date columnar M/D/YYYY"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if line.strip().lower() == 'date':
            for j in range(i + 1, min(i + 5, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


def _extract_serious_sanitation_date(text: str) -> Optional[str]:
    """Serious Sanitation - DATE columnar MM/DD/YYYY"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if line.strip().upper() == 'DATE':
            for j in range(i + 1, min(i + 10, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


def _extract_busy_bee_disposal_date(text: str) -> Optional[str]:
    """Busy Bee Disposal - TrashBilling Date: Weekday Mon D, YYYY inline"""
    text = _normalize_text(text)
    m = re.search(r'Date:\s*(?:Mon|Tue|Wed|Thu|Fri|Sat|Sun)\s+([A-Za-z]{3})\s+(\d{1,2}),?\s*(\d{4})', text)
    if m:
        month = MONTH_MAP.get(m.group(1).lower()[:3])
        if month:
            day, year = int(m.group(2)), int(m.group(3))
            if _validate_date(month, day, year):
                return _format_date(month, day, year)
    return None


def _extract_gils_sanitation_date(text: str) -> Optional[str]:
    """Gil's Sanitation - Invoice Date columnar M/DD/YYYY"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if 'invoice date' in line.lower():
            for j in range(i + 1, min(i + 5, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


def _extract_buckingham_companies_date(text: str) -> Optional[str]:
    """Buckingham Companies - Invoice Date: MM/DD/YYYY inline"""
    text = _normalize_text(text)
    m = re.search(r'Invoice\s+Date:\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})', text, re.IGNORECASE)
    if m:
        return _parse_date_match(m, 'MDY')
    return None


def _extract_city_of_baxley_date(text: str) -> Optional[str]:
    """City of Baxley - first M/DD/YYYY date in service dates section"""
    text = _normalize_text(text)
    m = re.search(r'(\d{1,2})[/\-](\d{1,2})[/\-](\d{4})', text)
    if m:
        return _parse_date_match(m, 'MDY')
    return None


def _extract_anchorage_solid_waste_date(text: str) -> Optional[str]:
    """Anchorage Solid Waste - BILL DATE: MM/DD/YYYY inline"""
    text = _normalize_text(text)
    m = re.search(r'BILL\s+DATE:\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})', text, re.IGNORECASE)
    if m:
        return _parse_date_match(m, 'MDY')
    return None


def _extract_hbs_denver_date(text: str) -> Optional[str]:
    """HBS Denver - INVOICE DATE columnar MM/DD/YYYY"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if 'invoice date' in line.lower():
            for j in range(i + 1, min(i + 5, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


def _extract_toro_waste_date(text: str) -> Optional[str]:
    """Toro Waste - first MM/DD/YYYY date near INVOICE header"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if 'invoice' in line.lower():
            for j in range(max(0, i - 3), min(i + 5, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


def _extract_north_port_solid_waste_date(text: str) -> Optional[str]:
    """North Port Solid Waste - BILL DATE columnar M/DD/YY"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if 'bill date' in line.lower():
            for j in range(i + 1, min(i + 10, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


def _extract_north_iredell_sanitation_date(text: str) -> Optional[str]:
    """North Iredell Sanitation - Date of issue Month DD, YYYY inline"""
    text = _normalize_text(text)
    m = re.search(r'Date\s+of\s+issue\s+([A-Za-z]+)\s+(\d{1,2}),?\s*(\d{4})', text, re.IGNORECASE)
    if m:
        month = MONTH_MAP.get(m.group(1).lower()[:3])
        if month:
            day, year = int(m.group(2)), int(m.group(3))
            if _validate_date(month, day, year):
                return _format_date(month, day, year)
    return None


# --- Tranche 86 ---

def _extract_city_of_craig_date(text: str) -> Optional[str]:
    """City of Craig - Billing Period End columnar MM/DD/YYYY"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if 'billing period end' in line.lower():
            for j in range(i + 1, min(i + 5, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


def _extract_prolex_compacting_date(text: str) -> Optional[str]:
    """Prolex Compacting - DATE MM/DD/YYYY inline"""
    text = _normalize_text(text)
    m = re.search(r'\bDATE\s+(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})', text)
    if m:
        return _parse_date_match(m, 'MDY')
    return None


def _extract_graybill_equipment_date(text: str) -> Optional[str]:
    """Graybill Equipment & Repair - Date columnar MM/DD/YYYY"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if line.strip().lower() == 'date':
            for j in range(i + 1, min(i + 5, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


def _extract_aspen_leasing_date(text: str) -> Optional[str]:
    """Aspen Leasing - Invoice Date MM/DD/YYYY inline"""
    text = _normalize_text(text)
    m = re.search(r'Invoice\s+Date\s+(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})', text, re.IGNORECASE)
    if m:
        return _parse_date_match(m, 'MDY')
    return None


def _extract_mid_ohio_sanitation_date(text: str) -> Optional[str]:
    """Mid-Ohio Sanitation & Recycling - TrashBilling Weekday Mon D, YYYY"""
    text = _normalize_text(text)
    m = re.search(r'(?:Mon|Tue|Wed|Thu|Fri|Sat|Sun)\s+([A-Za-z]{3})\s+(\d{1,2}),?\s*(\d{4})', text)
    if m:
        month = MONTH_MAP.get(m.group(1).lower()[:3])
        if month:
            day, year = int(m.group(2)), int(m.group(3))
            if _validate_date(month, day, year):
                return _format_date(month, day, year)
    return None


def _extract_jim_dedmans_sanitation_date(text: str) -> Optional[str]:
    """Jim Dedman's Sanitation - TrashBilling Date: Weekday Mon DD, YYYY inline"""
    text = _normalize_text(text)
    m = re.search(r'Date:\s*(?:Mon|Tue|Wed|Thu|Fri|Sat|Sun)\s+([A-Za-z]{3})\s+(\d{1,2}),?\s*(\d{4})', text)
    if m:
        month = MONTH_MAP.get(m.group(1).lower()[:3])
        if month:
            day, year = int(m.group(2)), int(m.group(3))
            if _validate_date(month, day, year):
                return _format_date(month, day, year)
    return None


def _extract_delta_disposal_date(text: str) -> Optional[str]:
    """Delta Disposal - TrashBilling Weekday Mon D, YYYY"""
    text = _normalize_text(text)
    m = re.search(r'(?:Mon|Tue|Wed|Thu|Fri|Sat|Sun)\s+([A-Za-z]{3})\s+(\d{1,2}),?\s*(\d{4})', text)
    if m:
        month = MONTH_MAP.get(m.group(1).lower()[:3])
        if month:
            day, year = int(m.group(2)), int(m.group(3))
            if _validate_date(month, day, year):
                return _format_date(month, day, year)
    return None


def _extract_redwood_landfill_date(text: str) -> Optional[str]:
    """Redwood Landfill - Invoice Date columnar Mon DD, YYYY"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if 'invoice date' in line.lower():
            for j in range(i + 1, min(i + 5, len(lines))):
                m = re.match(r'^\s*([A-Za-z]{3})\s+(\d{1,2}),?\s*(\d{4})\s*$', lines[j].strip())
                if m:
                    month = MONTH_MAP.get(m.group(1).lower()[:3])
                    if month:
                        day, year = int(m.group(2)), int(m.group(3))
                        if _validate_date(month, day, year):
                            return _format_date(month, day, year)
    return None


def _extract_city_of_scottsbluff_date(text: str) -> Optional[str]:
    """City of Scottsbluff - Billing Date columnar M/DD/YYYY"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if 'billing date' in line.lower():
            for j in range(i + 1, min(i + 5, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


def _extract_hughes_waste_haulers_date(text: str) -> Optional[str]:
    """Hughes Waste Haulers - Date columnar M/DD/YYYY"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if line.strip().lower() == 'date':
            for j in range(i + 1, min(i + 5, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


def _extract_mountain_high_disposal_date(text: str) -> Optional[str]:
    """Mountain High Disposal - Date columnar MM/DD/YYYY"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if line.strip().lower() == 'date':
            for j in range(i + 1, min(i + 10, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


def _extract_dumontelle_waste_date(text: str) -> Optional[str]:
    """DuMontelle Waste - Invoice date: MM/DD/YYYY inline"""
    text = _normalize_text(text)
    m = re.search(r'Invoice\s+date:\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})', text, re.IGNORECASE)
    if m:
        return _parse_date_match(m, 'MDY')
    return None


# --- Tranche 87 ---

def _extract_mogford_metals_date(text: str) -> Optional[str]:
    """Mogford Metals - Date: columnar MM/DD/YYYY"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if line.strip().lower() == 'date:':
            for j in range(i + 1, min(i + 5, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


def _extract_anaconda_disposal_date(text: str) -> Optional[str]:
    """Anaconda Disposal - TrashBilling Weekday Mon DD, YYYY"""
    text = _normalize_text(text)
    m = re.search(r'(?:Mon|Tue|Wed|Thu|Fri|Sat|Sun)\s+([A-Za-z]{3})\s+(\d{1,2}),?\s*(\d{4})', text)
    if m:
        month = MONTH_MAP.get(m.group(1).lower()[:3])
        if month:
            day, year = int(m.group(2)), int(m.group(3))
            if _validate_date(month, day, year):
                return _format_date(month, day, year)
    return None


def _extract_post_environmental_services_date(text: str) -> Optional[str]:
    """Post Environmental Services - Invoice date: MM/DD/YYYY inline"""
    text = _normalize_text(text)
    m = re.search(r'Invoice\s+date:\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})', text, re.IGNORECASE)
    if m:
        return _parse_date_match(m, 'MDY')
    return None


def _extract_virgin_valley_disposal_date(text: str) -> Optional[str]:
    """Virgin Valley Disposal - INVOICE DATE: M/DD/YYYY inline"""
    text = _normalize_text(text)
    m = re.search(r'INVOICE\s+DATE:\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})', text, re.IGNORECASE)
    if m:
        return _parse_date_match(m, 'MDY')
    return None


def _extract_wm_collection_date(text: str) -> Optional[str]:
    """WM Collection - Invoice Date: columnar MM/DD/YYYY (wide)"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if 'invoice date' in line.lower():
            for j in range(i + 1, min(i + 10, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


def _extract_american_metal_and_paper_date(text: str) -> Optional[str]:
    """American Metal & Paper - Invoice Date: MM/DD/YYYY inline"""
    text = _normalize_text(text)
    m = re.search(r'Invoice\s+Date:\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})', text, re.IGNORECASE)
    if m:
        return _parse_date_match(m, 'MDY')
    return None


def _extract_united_waste_haulers_date(text: str) -> Optional[str]:
    """United Waste Haulers - INVOICE DATE reverse columnar MM/DD/YYYY"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if 'invoice date' in line.lower():
            for j in range(max(0, i - 3), i):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


def _extract_walker_garbage_and_recycling_date(text: str) -> Optional[str]:
    """Walker Garbage and Recycling - Bill Date MM/DD/YY inline"""
    text = _normalize_text(text)
    m = re.search(r'Bill\s+Date\s+(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})', text, re.IGNORECASE)
    if m:
        return _parse_date_match(m, 'MDY')
    return None


def _extract_tnr_hauling_date(text: str) -> Optional[str]:
    """TNR Hauling - Invoice date: MM/DD/YYYY inline"""
    text = _normalize_text(text)
    m = re.search(r'Invoice\s+date:\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})', text, re.IGNORECASE)
    if m:
        return _parse_date_match(m, 'MDY')
    return None


def _extract_city_of_yuma_date(text: str) -> Optional[str]:
    """City of Yuma - BILLING DATE: columnar MM/DD/YYYY"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if 'billing date' in line.lower():
            for j in range(i + 1, min(i + 5, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


def _extract_mills_bros_date(text: str) -> Optional[str]:
    """Mills Bros - STATEMENT DATE: columnar MM/DD/YY"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if 'statement date' in line.lower():
            for j in range(i + 1, min(i + 5, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


def _extract_tomorrow_rds_date(text: str) -> Optional[str]:
    """Tomorrow RDS - DATE reverse columnar MM/DD/YYYY"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if line.strip().upper() == 'DATE':
            for j in range(max(0, i - 5), i):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


# --- Tranche 88 ---

def _extract_ewe_equipment_date(text: str) -> Optional[str]:
    """EWE Equipment - Invoice Date columnar MM/DD/YY"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if 'invoice date' in line.lower():
            for j in range(i + 1, min(i + 5, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


def _extract_flash_trash_date(text: str) -> Optional[str]:
    """Flash Trash - DATE columnar MM/DD/YYYY"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if line.strip().upper() == 'DATE':
            for j in range(i + 1, min(i + 5, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


def _extract_city_of_barstow_date(text: str) -> Optional[str]:
    """City of Barstow - BILL DATE columnar MM/DD/YYYY (wide)"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if 'bill date' in line.lower():
            for j in range(i + 1, min(i + 8, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


def _extract_civicorps_recycling_date(text: str) -> Optional[str]:
    """Civicorps Recycling - Date of Issue columnar MM/DD/YYYY"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if 'date of issue' in line.lower():
            for j in range(i + 1, min(i + 5, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


def _extract_ps_trucking_date(text: str) -> Optional[str]:
    """P&S Trucking - Issue date columnar Mon DD, YYYY"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if 'issue date' in line.lower():
            for j in range(i + 1, min(i + 5, len(lines))):
                m = re.match(r'^\s*([A-Za-z]{3,9})\s+(\d{1,2}),?\s*(\d{4})\s*$', lines[j].strip())
                if m:
                    month = MONTH_MAP.get(m.group(1).lower()[:3])
                    if month:
                        day, year = int(m.group(2)), int(m.group(3))
                        if _validate_date(month, day, year):
                            return _format_date(month, day, year)
    return None


def _extract_white_mountain_apache_date(text: str) -> Optional[str]:
    """White Mountain Apache - Date: M/D/YYYY inline"""
    text = _normalize_text(text)
    m = re.search(r'Date:\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})', text, re.IGNORECASE)
    if m:
        return _parse_date_match(m, 'MDY')
    return None


def _extract_evergreen_paper_recycling_date(text: str) -> Optional[str]:
    """Evergreen Paper Recycling - DATE columnar MM/DD/YYYY"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if line.strip().upper() == 'DATE':
            for j in range(i + 1, min(i + 5, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


def _extract_rahn_sanitary_date(text: str) -> Optional[str]:
    """Rahn Sanitary - Bill Date: reverse columnar MM/DD/YYYY"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if 'bill date' in line.lower():
            for j in range(max(0, i - 3), i):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


def _extract_maguire_equipment_date(text: str) -> Optional[str]:
    """Maguire Equipment - Date columnar M/D/YYYY (wide)"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if line.strip().lower() == 'date':
            for j in range(i + 1, min(i + 5, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


def _extract_cook_sanitation_date(text: str) -> Optional[str]:
    """Cook Sanitation - Bill Date: M/DD/YY inline"""
    text = _normalize_text(text)
    m = re.search(r'Bill\s+Date:\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})', text, re.IGNORECASE)
    if m:
        return _parse_date_match(m, 'MDY')
    return None


def _extract_eagle_equipment_corporation_date(text: str) -> Optional[str]:
    """Eagle Equipment Corporation - INVOICE DATE columnar MM/DD/YY"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if 'invoice date' in line.lower():
            for j in range(i + 1, min(i + 5, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


def _extract_big_bear_disposal_date(text: str) -> Optional[str]:
    """Big Bear Disposal - INVOICE DATE columnar M/D/YYYY (wide)"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if 'invoice date' in line.lower():
            for j in range(i + 1, min(i + 5, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


# --- Tranche 89 ---

def _extract_city_of_lake_mary_date(text: str) -> Optional[str]:
    """City of Lake Mary - Bill Date columnar MM/DD/YY (wide)"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if 'bill date' in line.lower():
            for j in range(i + 1, min(i + 5, len(lines))):
                m = re.match(r'^\s*(?:\d{2}-\d{2}\s+)?(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


def _extract_generated_materials_recovery_date(text: str) -> Optional[str]:
    """Generated Materials Recovery - Invoice Date reverse columnar MM/DD/YY"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if 'invoice date' in line.lower():
            for j in range(max(0, i - 3), i):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


def _extract_styro_recycle_date(text: str) -> Optional[str]:
    """Styro Recycle - Date columnar MM/DD/YYYY"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if line.strip().lower() == 'date':
            for j in range(i + 1, min(i + 5, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


def _extract_buldo_container_disposal_date(text: str) -> Optional[str]:
    """Buldo Container & Disposal - DATE reverse columnar DD-Mon-YYYY"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if line.strip().upper() == 'DATE':
            for j in range(max(0, i - 3), i):
                m = re.match(r'^\s*(\d{1,2})-([A-Za-z]{3})-(\d{4})\s*$', lines[j].strip())
                if m:
                    month = MONTH_MAP.get(m.group(2).lower()[:3])
                    if month:
                        day, year = int(m.group(1)), int(m.group(3))
                        if _validate_date(month, day, year):
                            return _format_date(month, day, year)
    return None


def _extract_desert_green_disposal_date(text: str) -> Optional[str]:
    """Desert Green Disposal - Date columnar M/D/YYYY"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if line.strip().lower() == 'date':
            for j in range(i + 1, min(i + 8, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


def _extract_capital_area_refuse_date(text: str) -> Optional[str]:
    """Capital Area Refuse - TrashBilling received on M/D/YYYY"""
    text = _normalize_text(text)
    m = re.search(r'received\s+on\s+(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})', text, re.IGNORECASE)
    if m:
        return _parse_date_match(m, 'MDY')
    return None


def _extract_city_of_lebanon_date(text: str) -> Optional[str]:
    """City of Lebanon - DATE: Month DD, YYYY inline"""
    text = _normalize_text(text)
    m = re.search(r'DATE:\s*([A-Za-z]+)\s+(\d{1,2}),?\s*(\d{4})', text, re.IGNORECASE)
    if m:
        month = MONTH_MAP.get(m.group(1).lower()[:3])
        if month:
            day, year = int(m.group(2)), int(m.group(3))
            if _validate_date(month, day, year):
                return _format_date(month, day, year)
    return None


def _extract_liberty_ashes_date(text: str) -> Optional[str]:
    """Liberty Ashes - TrashBilling Weekday Mon DD, YYYY"""
    text = _normalize_text(text)
    m = re.search(r'(?:Mon|Tue|Wed|Thu|Fri|Sat|Sun)\s+([A-Za-z]{3})\s+(\d{1,2}),?\s*(\d{4})', text)
    if m:
        month = MONTH_MAP.get(m.group(1).lower()[:3])
        if month:
            day, year = int(m.group(2)), int(m.group(3))
            if _validate_date(month, day, year):
                return _format_date(month, day, year)
    return None


def _extract_kluesner_sanitation_date(text: str) -> Optional[str]:
    """Kluesner Sanitation - Invoice Date columnar MM/DD/YYYY"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if 'invoice date' in line.lower():
            for j in range(i + 1, min(i + 8, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


def _extract_g_h_garbage_date(text: str) -> Optional[str]:
    """G & H Garbage - INV DATE columnar MM/DD/YY"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if 'inv date' in line.lower():
            for j in range(i + 1, min(i + 5, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


def _extract_seagraves_plumbing_date(text: str) -> Optional[str]:
    """Seagraves Plumbing - Invoice Date: Mon D, YYYY inline"""
    text = _normalize_text(text)
    m = re.search(r'Invoice\s+Date:\s*([A-Za-z]{3})\s+(\d{1,2}),?\s*(\d{4})', text, re.IGNORECASE)
    if m:
        month = MONTH_MAP.get(m.group(1).lower()[:3])
        if month:
            day, year = int(m.group(2)), int(m.group(3))
            if _validate_date(month, day, year):
                return _format_date(month, day, year)
    return None


def _extract_lakeside_recycling_date(text: str) -> Optional[str]:
    """Lakeside Recycling - TrashBilling Weekday Mon DD, YYYY"""
    text = _normalize_text(text)
    m = re.search(r'(?:Mon|Tue|Wed|Thu|Fri|Sat|Sun)\s+([A-Za-z]{3})\s+(\d{1,2}),?\s*(\d{4})', text)
    if m:
        month = MONTH_MAP.get(m.group(1).lower()[:3])
        if month:
            day, year = int(m.group(2)), int(m.group(3))
            if _validate_date(month, day, year):
                return _format_date(month, day, year)
    return None


# --- Tranche 90 ---

def _extract_columbia_county_solid_waste_date(text: str) -> Optional[str]:
    """Columbia County Solid Waste - INVOICE DATE columnar MM/DD/YYYY"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if 'invoice date' in line.lower():
            for j in range(i + 1, min(i + 5, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


def _extract_thomas_trash_date(text: str) -> Optional[str]:
    """Thomas Trash - INV DATE columnar MM/DD/YY"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if 'inv date' in line.lower():
            for j in range(i + 1, min(i + 5, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


def _extract_town_of_babylon_date(text: str) -> Optional[str]:
    """Town of Babylon - Invoice Date columnar MM/DD/YYYY (wide)"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if 'invoice date' in line.lower():
            for j in range(i + 1, min(i + 5, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


def _extract_harley_hollan_date(text: str) -> Optional[str]:
    """Harley Hollan - Invoice Date: MM/DD/YYYY inline"""
    text = _normalize_text(text)
    m = re.search(r'Invoice\s+Date:\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})', text, re.IGNORECASE)
    if m:
        return _parse_date_match(m, 'MDY')
    return None


def _extract_fiber_services_date(text: str) -> Optional[str]:
    """Fiber Services - statement period start MM/DD/YYYY"""
    text = _normalize_text(text)
    m = re.search(r'(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s+To\s+\d{1,2}[/\-]\d{1,2}[/\-]\d{2,4}', text, re.IGNORECASE)
    if m:
        return _parse_date_match(m, 'MDY')
    return None


def _extract_city_of_redwood_date(text: str) -> Optional[str]:
    """City of Redwood - Billed: columnar MM/DD/YY"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if 'billed:' in line.lower():
            for j in range(i + 1, min(i + 5, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


def _extract_city_of_dickson_date(text: str) -> Optional[str]:
    """City of Dickson - DATE MM/DD/YYYY inline"""
    text = _normalize_text(text)
    m = re.search(r'\bDATE\s+(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})', text, re.IGNORECASE)
    if m:
        return _parse_date_match(m, 'MDY')
    return None


def _extract_dans_r_us_sanitation_date(text: str) -> Optional[str]:
    """Dan's R Us Sanitation - Invoice Date: MM/DD/YYYY inline"""
    text = _normalize_text(text)
    m = re.search(r'Invoice\s+Date:\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})', text, re.IGNORECASE)
    if m:
        return _parse_date_match(m, 'MDY')
    return None


def _extract_roller_industrial_date(text: str) -> Optional[str]:
    """Roller Industrial - DATE columnar M/DD/YYYY (wide)"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if line.strip().upper() == 'DATE':
            for j in range(i + 1, min(i + 8, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


def _extract_res_waste_date(text: str) -> Optional[str]:
    """RES Waste - Date columnar MM/DD/YYYY"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if line.strip().lower() == 'date':
            for j in range(i + 1, min(i + 5, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


def _extract_city_of_hidalgo_date(text: str) -> Optional[str]:
    """City of Hidalgo - Billing Date columnar M/DD/YYYY"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if 'billing date' in line.lower():
            for j in range(i + 1, min(i + 5, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


def _extract_city_of_huron_date(text: str) -> Optional[str]:
    """City of Huron - BILLING DATE columnar MM/DD/YY"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if 'billing date' in line.lower():
            for j in range(i + 1, min(i + 5, len(lines))):
                m = re.search(r'(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})', lines[j])
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


# --- Tranche 91 ---

def _extract_horn_sanitation_date(text: str) -> Optional[str]:
    """Horn Sanitation - Issued columnar Mon DD, YYYY"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if line.strip().lower() == 'issued':
            for j in range(i + 1, min(i + 5, len(lines))):
                m = re.match(r'^\s*([A-Za-z]{3,9})\s+(\d{1,2}),?\s*(\d{4})\s*$', lines[j].strip())
                if m:
                    month = MONTH_MAP.get(m.group(1).lower()[:3])
                    if month:
                        day, year = int(m.group(2)), int(m.group(3))
                        if _validate_date(month, day, year):
                            return _format_date(month, day, year)
    return None


def _extract_sutter_disposal_date(text: str) -> Optional[str]:
    """Sutter Disposal - TrashBilling Weekday Mon D, YYYY"""
    text = _normalize_text(text)
    m = re.search(r'(?:Mon|Tue|Wed|Thu|Fri|Sat|Sun)\s+([A-Za-z]{3})\s+(\d{1,2}),?\s*(\d{4})', text)
    if m:
        month = MONTH_MAP.get(m.group(1).lower()[:3])
        if month:
            day, year = int(m.group(2)), int(m.group(3))
            if _validate_date(month, day, year):
                return _format_date(month, day, year)
    return None


def _extract_self_recycling_date(text: str) -> Optional[str]:
    """Self Recycling - Date columnar M/DD/YYYY"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if line.strip().lower() == 'date':
            for j in range(i + 1, min(i + 8, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


def _extract_nisly_brothers_date(text: str) -> Optional[str]:
    """Nisly Brothers - DATE columnar Mon DD, YYYY"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if line.strip().upper() == 'DATE':
            for j in range(i + 1, min(i + 8, len(lines))):
                m = re.match(r'^\s*([A-Za-z]{3,9})\s+(\d{1,2}),?\s*(\d{4})\s*$', lines[j].strip())
                if m:
                    month = MONTH_MAP.get(m.group(1).lower()[:3])
                    if month:
                        day, year = int(m.group(2)), int(m.group(3))
                        if _validate_date(month, day, year):
                            return _format_date(month, day, year)
    return None


def _extract_al_compaction_date(text: str) -> Optional[str]:
    """A&L Compaction - Date columnar M/DD/YYYY"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if line.strip().lower() == 'date':
            for j in range(i + 1, min(i + 8, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


def _extract_macs_wood_products_date(text: str) -> Optional[str]:
    """Mac's Wood Products - first MM/DD/YYYY after INVOICE"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if 'invoice' in line.lower():
            for j in range(i + 1, min(i + 5, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


def _extract_eagle_equipment_service_1_date(text: str) -> Optional[str]:
    """Eagle Equipment Service 1 - DATE MM/DD/YYYY inline"""
    text = _normalize_text(text)
    m = re.search(r'\bDATE\s+(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})', text, re.IGNORECASE)
    if m:
        return _parse_date_match(m, 'MDY')
    return None


def _extract_boulder_city_disposal_date(text: str) -> Optional[str]:
    """Boulder City Disposal - Statement Date: MM/DD/YY inline"""
    text = _normalize_text(text)
    m = re.search(r'Statement\s+Date:\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})', text, re.IGNORECASE)
    if m:
        return _parse_date_match(m, 'MDY')
    return None


def _extract_city_of_loganville_date(text: str) -> Optional[str]:
    """City of Loganville - Bill Date columnar MM/DD/YYYY"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if 'bill date' in line.lower():
            for j in range(i + 1, min(i + 10, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


def _extract_pak_rite_rentals_date(text: str) -> Optional[str]:
    """Pak-Rite Rentals - Date columnar M/D/YYYY"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if line.strip().lower() == 'date':
            for j in range(i + 1, min(i + 5, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


def _extract_town_of_greeneville_date(text: str) -> Optional[str]:
    """Town of Greeneville - Service Period start MM/DD/YYYY"""
    text = _normalize_text(text)
    m = re.search(r'(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*-\s*\d{1,2}[/\-]\d{1,2}[/\-]\d{2,4}', text)
    if m:
        return _parse_date_match(m, 'MDY')
    return None


def _extract_davids_trash_service_date(text: str) -> Optional[str]:
    """David's Trash Service - TrashBilling Weekday Mon DD, YYYY"""
    text = _normalize_text(text)
    m = re.search(r'(?:Mon|Tue|Wed|Thu|Fri|Sat|Sun)\s+([A-Za-z]{3})\s+(\d{1,2}),?\s*(\d{4})', text)
    if m:
        month = MONTH_MAP.get(m.group(1).lower()[:3])
        if month:
            day, year = int(m.group(2)), int(m.group(3))
            if _validate_date(month, day, year):
                return _format_date(month, day, year)
    return None


# --- Tranche 92 ---

def _extract_city_of_enumclaw_date(text: str) -> Optional[str]:
    """City of Enumclaw - DATE BILLED columnar MM/DD/YY"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if 'date billed' in line.lower():
            for j in range(i + 1, min(i + 5, len(lines))):
                m = re.search(r'(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})', lines[j])
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


def _extract_johnson_city_utility_date(text: str) -> Optional[str]:
    """Johnson City Utility - SERVICE FROM columnar MM-DD-YY"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if 'service from' in line.lower():
            for j in range(i + 1, min(i + 3, len(lines))):
                m = re.match(r'^\s*(\d{1,2})-(\d{1,2})-(\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


def _extract_first_capitol_salvage_date(text: str) -> Optional[str]:
    """First Capitol Salvage - INVOICE DATE columnar MM/DD/YYYY (wide)"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if 'invoice date' in line.lower():
            for j in range(i + 1, min(i + 5, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


def _extract_excess_disposal_date(text: str) -> Optional[str]:
    """Excess Disposal - Billing Date columnar M/DD/YYYY"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if 'billing date' in line.lower():
            for j in range(i + 1, min(i + 3, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


def _extract_dirty_boyz_sanitation_date(text: str) -> Optional[str]:
    """Dirty Boyz Sanitation - Service Date MM/DD/YYYY inline"""
    text = _normalize_text(text)
    m = re.search(r'Service\s+Date\s+(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})', text, re.IGNORECASE)
    if m:
        return _parse_date_match(m, 'MDY')
    return None


def _extract_cliffs_commercial_trash_date(text: str) -> Optional[str]:
    """Cliff's Commercial Trash - Date columnar M/DD/YYYY"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if line.strip().lower() == 'date':
            for j in range(i + 1, min(i + 8, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


def _extract_jj_sanitation_date(text: str) -> Optional[str]:
    """J&J Sanitation - STATEMENT DATE columnar MM/DD/YY (wide)"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if 'statement date' in line.lower():
            for j in range(i + 1, min(i + 8, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


def _extract_srg_spartanburg_date(text: str) -> Optional[str]:
    """SRG Spartanburg - Inv Date: MM/DD/YYYY inline"""
    text = _normalize_text(text)
    m = re.search(r'Inv\s+Date:\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})', text, re.IGNORECASE)
    if m:
        return _parse_date_match(m, 'MDY')
    return None


def _extract_kept_companies_date(text: str) -> Optional[str]:
    """Kept Companies - Date: columnar Month DD, YYYY"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if line.strip().lower() == 'date:':
            for j in range(i + 1, min(i + 3, len(lines))):
                m = re.match(r'^\s*([A-Za-z]+)\s+(\d{1,2}),?\s*(\d{4})\s*$', lines[j].strip())
                if m:
                    month = MONTH_MAP.get(m.group(1).lower()[:3])
                    if month:
                        day, year = int(m.group(2)), int(m.group(3))
                        if _validate_date(month, day, year):
                            return _format_date(month, day, year)
    return None


def _extract_c_h_disposal_date(text: str) -> Optional[str]:
    """C & H Disposal - DATE columnar M/D/YYYY"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if line.strip().upper() == 'DATE':
            for j in range(i + 1, min(i + 8, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


def _extract_lci_services_date(text: str) -> Optional[str]:
    """LCI Services - Invoice Date: MM/DD/YYYY inline"""
    text = _normalize_text(text)
    m = re.search(r'Invoice\s+Date:\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})', text, re.IGNORECASE)
    if m:
        return _parse_date_match(m, 'MDY')
    return None


def _extract_hudgins_disposal_date(text: str) -> Optional[str]:
    """Hudgins Disposal - TrashBilling received on M/D/YYYY"""
    text = _normalize_text(text)
    m = re.search(r'received\s+on\s+(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})', text, re.IGNORECASE)
    if m:
        return _parse_date_match(m, 'MDY')
    return None


# --- Tranche 93 ---

def _extract_hopper_disposal_date(text: str) -> Optional[str]:
    """Hopper Disposal - Date columnar MM/DD/YYYY"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if line.strip().lower() == 'date':
            for j in range(i + 1, min(i + 3, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


def _extract_desert_valley_disposal_date(text: str) -> Optional[str]:
    """Desert Valley Disposal - first MM/DD/YY date"""
    text = _normalize_text(text)
    m = re.search(r'(\d{1,2})[/\-](\d{1,2})[/\-](\d{2})\b', text)
    if m:
        return _parse_date_match(m, 'MDY')
    return None


def _extract_solid_waste_disposal_authority_date(text: str) -> Optional[str]:
    """Solid Waste Disposal Authority - BILLING DATE: columnar MM/DD/YYYY"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if 'billing date' in line.lower():
            for j in range(i + 1, min(i + 5, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


def _extract_my_green_michigan_date(text: str) -> Optional[str]:
    """My Green Michigan - Invoice date: MM/DD/YYYY inline"""
    text = _normalize_text(text)
    m = re.search(r'Invoice\s+date:\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})', text, re.IGNORECASE)
    if m:
        return _parse_date_match(m, 'MDY')
    return None


def _extract_mauldin_trash_date(text: str) -> Optional[str]:
    """Mauldin Trash - DATE columnar M/D/YYYY"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if line.strip().upper() == 'DATE':
            for j in range(i + 1, min(i + 3, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


def _extract_redfish_recycling_date(text: str) -> Optional[str]:
    """Redfish Recycling - Payment date columnar MM/DD/YYYY"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if 'payment date' in line.lower():
            for j in range(i + 1, min(i + 8, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


def _extract_carrier_container_date(text: str) -> Optional[str]:
    """Carrier Container - DATE columnar MM/DD/YYYY"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if line.strip().upper() == 'DATE':
            for j in range(i + 1, min(i + 3, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


def _extract_ds_waste_date(text: str) -> Optional[str]:
    """D&S Waste - INV DATE columnar MM/DD/YY"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if 'inv date' in line.lower():
            for j in range(i + 1, min(i + 3, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


def _extract_ljp_waste_date(text: str) -> Optional[str]:
    """LJP Waste - Date columnar MM/DD/YYYY"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if line.strip().lower() == 'date':
            for j in range(i + 1, min(i + 5, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


def _extract_hesco_hydraulic_date(text: str) -> Optional[str]:
    """HESCO Hydraulic - first MM/DD/YYYY date"""
    text = _normalize_text(text)
    m = re.search(r'(\d{2})[/\-](\d{2})[/\-](\d{4})', text)
    if m:
        return _parse_date_match(m, 'MDY')
    return None


def _extract_city_of_henagar_date(text: str) -> Optional[str]:
    """City of Henagar - Date columnar MM/DD/YYYY"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if line.strip().lower() == 'date':
            for j in range(i + 1, min(i + 5, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


def _extract_waste_partners_date(text: str) -> Optional[str]:
    """Waste Partners - INV DATE columnar MM/DD/YY"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if 'inv date' in line.lower():
            for j in range(i + 1, min(i + 3, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


# --- Tranche 94 ---

def _extract_tate_services_date(text: str) -> Optional[str]:
    """Tate Services - INVOICE DATE columnar M/D/YYYY"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if 'invoice date' in line.lower():
            for j in range(i + 1, min(i + 3, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


def _extract_local_waste_of_upstate_date(text: str) -> Optional[str]:
    """Local Waste of Upstate - Mon DD, YYYY format"""
    text = _normalize_text(text)
    m = re.search(r'([A-Za-z]{3})\s+(\d{1,2}),?\s*(\d{4})', text)
    if m:
        month = MONTH_MAP.get(m.group(1).lower()[:3])
        if month:
            day, year = int(m.group(2)), int(m.group(3))
            if _validate_date(month, day, year):
                return _format_date(month, day, year)
    return None


def _extract_fritz_enterprises_date(text: str) -> Optional[str]:
    """Fritz Enterprises - DATE reverse columnar MM/DD/YYYY (date before label)"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if line.strip().upper() == 'DATE':
            # Date is BEFORE the DATE label
            for j in range(max(0, i - 5), i):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


def _extract_island_recycling_date(text: str) -> Optional[str]:
    """Island Recycling - DATE columnar M/D/YYYY (wide spacing)"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if line.strip().upper() == 'DATE':
            for j in range(i + 1, min(i + 10, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


def _extract_sphuler_disposal_date(text: str) -> Optional[str]:
    """Sphuler Disposal - DATE inline MM/DD/YYYY"""
    text = _normalize_text(text)
    m = re.search(r'DATE\s+(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})', text, re.IGNORECASE)
    if m:
        return _parse_date_match(m, 'MDY')
    return None


def _extract_brookings_dumpster_service_date(text: str) -> Optional[str]:
    """Brookings Dumpster Service - Date columnar M/D/YYYY"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if line.strip().lower() == 'date':
            for j in range(i + 1, min(i + 5, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None


def _extract_harper_sanitation_date(text: str) -> Optional[str]:
    """Harper Sanitation - TrashBilling Weekday Mon DD, YYYY"""
    text = _normalize_text(text)
    m = re.search(r'(Mon|Tue|Wed|Thu|Fri|Sat|Sun)\s+([A-Za-z]{3})\s+(\d{1,2}),?\s*(\d{4})', text)
    if m:
        month = MONTH_MAP.get(m.group(2).lower()[:3])
        if month:
            day, year = int(m.group(3)), int(m.group(4))
            if _validate_date(month, day, year):
                return _format_date(month, day, year)
    return None


# =============================================================================
# VENDOR ADDITIONS DICTIONARY
# =============================================================================

VENDOR_DATE_ADDITIONS = {
    'Waste Connections': {
        'format': 'MM/DD/YY',
        'label': 'STATEMENT DATE',
        'examples': ['01/15/26', '12/31/25'],
        'extract': _extract_waste_connections_date
    },
    'Republic Services': {
        'format': 'MM/DD/YYYY',
        'label': 'Invoice Date',
        'examples': ['01/15/2025', '12/31/2024'],
        'extract': _extract_republic_date
    },
    'Waste Management': {
        'format': 'MM/DD/YYYY or Month DD, YYYY',
        'label': 'Invoice Date / Bill Date',
        'examples': ['01/15/2025', 'January 15, 2025'],
        'extract': _extract_waste_management_date
    },
    'GFL': {
        'format': 'MM/DD/YYYY',
        'label': 'INVOICE DATE',
        'examples': ['12/31/2024'],
        'extract': _extract_gfl_date
    },
    'Rumpke': {
        'format': 'MM/DD/YY',
        'label': 'Invoice Date',
        'examples': ['01/15/25'],
        'extract': _extract_rumpke_date
    },
    'Casella': {
        'format': 'MM/DD/YYYY',
        'label': 'Date',
        'examples': ['01/15/2025'],
        'extract': _extract_casella_date
    },
    'FCC Environmental': {
        'format': 'MM/DD/YYYY',
        'label': 'Invoice Date',
        'examples': ['01/15/2025'],
        'extract': _extract_fcc_date
    },
    'Tiger Sanitation': {
        'format': 'MM/DD/YYYY',
        'label': 'Invoice Date',
        'examples': ['01/15/2025'],
        'extract': _extract_tiger_date
    },
    'Anytime Waste': {
        'format': 'Month DD, YYYY',
        'label': 'DATE',
        'examples': ['Apr 30, 2025'],
        'extract': _extract_anytime_waste_date
    },
    # === TRANCHE 2 (February 2026) ===
    'Meridian Waste': {
        'format': 'MM/DD/YYYY',
        'label': 'Date',
        'examples': ['10/15/2025'],
        'extract': _extract_meridian_waste_date
    },
    'Waste Pro': {
        'format': 'MM/DD/YYYY',
        'label': 'Invoice Date',
        'examples': ['01/15/2025'],
        'extract': _extract_waste_pro_date
    },
    'Athens Services': {
        'format': 'MM/DD/YYYY',
        'label': 'INVOICE DATE',
        'examples': ['01/15/2025'],
        'extract': _extract_athens_date
    },
    'Recology': {
        'format': 'MM/DD/YYYY',
        'label': 'Bill Date',
        'examples': ['03/31/2025'],
        'extract': _extract_recology_date
    },
    'Universal Waste': {
        'format': 'MM/DD/YY',
        'label': 'Invoice Date',
        'examples': ['12/31/25'],
        'extract': _extract_universal_waste_date
    },
    'Suburban Disposal': {
        'format': 'MM/DD/YY',
        'label': 'DATE',
        'examples': ['03/01/25'],
        'extract': _extract_suburban_disposal_date
    },
    'Lakeshore Recycling': {
        'format': 'MM/DD/YYYY',
        'label': 'Invoice Date / Statement Date',
        'examples': ['01/15/2025'],
        'extract': _extract_lakeshore_date
    },
    'County Waste': {
        'format': 'MM/DD/YYYY',
        'label': 'Invoice Date',
        'examples': ['01/15/2025'],
        'extract': _extract_county_waste_date
    },
    'Granger': {
        'format': 'MM/DD/YYYY',
        'label': 'Invoice Date',
        'examples': ['01/15/2025'],
        'extract': _extract_granger_date
    },
    'Advanced Disposal': {
        'format': 'MM/DD/YYYY',
        'label': 'Invoice Date / Statement Date',
        'examples': ['01/15/2025'],
        'extract': _extract_advanced_disposal_date
    },
    'Groot Industries': {
        'format': 'MM/DD/YYYY',
        'label': 'Invoice Date',
        'examples': ['01/15/2025'],
        'extract': _extract_groot_date
    },
    # === TRANCHE 3 (February 2026) ===
    'Emterra Environmental': {
        'format': 'Month DD, YYYY',
        'label': 'DATE',
        'examples': ['May 1, 2025'],
        'extract': _extract_emterra_date
    },
    'Robinson Waste': {
        'format': 'MM/DD/YYYY',
        'label': 'DATE',
        'examples': ['11/01/2025'],
        'extract': _extract_robinson_waste_date
    },
    'Lightning Disposal': {
        'format': 'MM/DD/YYYY',
        'label': 'DATE',
        'examples': ['05/14/2025'],
        'extract': _extract_lightning_disposal_date
    },
    'All Waste': {
        'format': 'MM/DD/YYYY',
        'label': 'Invoice Date',
        'examples': ['01/02/2025'],
        'extract': _extract_all_waste_date
    },
    # === TRANCHE 4 (February 2026) ===
    'Debris to Green': {
        'format': 'M/DD/YY',
        'label': 'DATE',
        'examples': ['4/16/25'],
        'extract': _extract_debris_to_green_date
    },
    'Disposal Management': {
        'format': 'MM/DD/YY',
        'label': 'INV DATE',
        'examples': ['07/01/25'],
        'extract': _extract_disposal_management_date
    },
    'KnightHorst': {
        'format': 'MM/DD/YYYY',
        'label': 'DATE',
        'examples': ['03/31/2025'],
        'extract': _extract_knighthorst_date
    },
    'Western Kane County': {
        'format': 'M/DD/YYYY',
        'label': 'Invoice Date',
        'examples': ['2/28/2025'],
        'extract': _extract_western_kane_date
    },
    'Panzarella Waste': {
        'format': 'MM/DD/YYYY',
        'label': 'Date',
        'examples': ['04/28/2025'],
        'extract': _extract_panzarella_date
    },
    'Sunrise Sanitation': {
        'format': 'M/DD/YYYY',
        'label': 'Date',
        'examples': ['4/30/2025'],
        'extract': _extract_sunrise_sanitation_date
    },
    'USA Waste': {
        'format': 'MM/DD/YYYY',
        'label': 'INVOICE DATE',
        'examples': ['10/01/2025'],
        'extract': _extract_usa_waste_date
    },
    'Best Cleaner': {
        'format': 'Weekday Month DD, YYYY',
        'label': 'inline date',
        'examples': ['Tue Sep 16, 2025'],
        'extract': _extract_best_cleaner_date
    },
    # === TRANCHE 5 (February 2026) ===
    'Bulldog Disposal': {
        'format': 'MM/DD/YY',
        'label': 'INV DATE',
        'examples': ['05/15/25'],
        'extract': _extract_bulldog_disposal_date
    },
    "Cockey's Enterprises": {
        'format': 'MM/DD/YYYY',
        'label': 'DATE',
        'examples': ['05/15/2025'],
        'extract': _extract_cockeys_date
    },
    'SBC Waste': {
        'format': 'MM/DD/YYYY',
        'label': 'Invoice Date',
        'examples': ['05/15/2025'],
        'extract': _extract_sbc_waste_date
    },
    'Walters Recycling': {
        'format': 'M/DD/YYYY',
        'label': 'INVOICE DATE',
        'examples': ['5/10/2025'],
        'extract': _extract_walters_date
    },
    'TransTrash': {
        'format': 'Month DD, YYYY',
        'label': 'DATE / DUE DATE',
        'examples': ['May 31, 2025'],
        'extract': _extract_transtrash_date
    },
    'Conigliaro': {
        'format': 'MM/DD/YYYY',
        'label': 'Date',
        'examples': ['08/28/2025'],
        'extract': _extract_conigliaro_date
    },
    'Wompost': {
        'format': 'M/DD/YYYY',
        'label': 'STATEMENT DATE',
        'examples': ['4/24/2025'],
        'extract': _extract_wompost_date
    },
    'Boren Brothers': {
        'format': 'M/D/YYYY',
        'label': 'INVOICE DATE',
        'examples': ['8/1/2025'],
        'extract': _extract_boren_brothers_date
    },
    'South Shore Disposal': {
        'format': 'MM/DD/YY',
        'label': 'INV DATE',
        'examples': ['11/30/25'],
        'extract': _extract_south_shore_date
    },
    'Best Way Disposal': {
        'format': 'MM/DD/YYYY',
        'label': 'Invoice Date',
        'examples': ['01/15/2025'],
        'extract': _extract_best_way_date
    },
    # === TRANCHE 6 (February 2026) ===
    'Flood Brothers': {
        'format': 'MM/DD/YYYY',
        'label': 'BILLING DATE',
        'examples': ['03/06/2025'],
        'extract': _extract_flood_brothers_date
    },
    'Empire Waste': {
        'format': 'MM/DD/YYYY',
        'label': 'DATE',
        'examples': ['03/15/2025'],
        'extract': _extract_empire_waste_date
    },
    'Midwest Paper': {
        'format': 'MM/DD/YYYY',
        'label': 'DATE',
        'examples': ['03/15/2025'],
        'extract': _extract_midwest_paper_date
    },
    'Coastal Waste': {
        'format': 'MM/DD/YYYY',
        'label': 'Date',
        'examples': ['03/15/2025'],
        'extract': _extract_coastal_waste_date
    },
    'Standard Waste': {
        'format': 'MM/DD/YY',
        'label': 'Date',
        'examples': ['05/01/25'],
        'extract': _extract_standard_waste_date
    },
    'Frontier Waste': {
        'format': 'Month DD, YYYY',
        'label': 'DATE',
        'examples': ['Mar 15, 2025'],
        'extract': _extract_frontier_waste_date
    },
    'Waste Eliminator': {
        'format': 'MM/DD/YYYY',
        'label': 'Date',
        'examples': ['10/01/2025'],
        'extract': _extract_waste_eliminator_date
    },
    "Harter's": {
        'format': 'MM/DD/YYYY',
        'label': 'Invoice Date',
        'examples': ['01/31/2025'],
        'extract': _extract_harters_date
    },
    'Smith Creek': {
        'format': 'M/D/YYYY',
        'label': 'DATE',
        'examples': ['2/5/2025'],
        'extract': _extract_smith_creek_date
    },
    'Aspen Waste': {
        'format': 'MM/DD/YYYY',
        'label': 'Statement Date',
        'examples': ['03/01/2025'],
        'extract': _extract_aspen_waste_date
    },
    'Active Waste': {
        'format': 'MM/DD/YYYY',
        'label': 'DATE',
        'examples': ['03/15/2025'],
        'extract': _extract_active_waste_date
    },
    # === TRANCHE 7 (February 2026) ===
    'Hamilton Alliance': {
        'format': 'M/DD/YYYY',
        'label': 'Date',
        'examples': ['3/31/2025'],
        'extract': _extract_hamilton_alliance_date
    },
    'Priority Waste': {
        'format': 'M/DD/YYYY',
        'label': 'Date:',
        'examples': ['3/31/2025'],
        'extract': _extract_priority_waste_date
    },
    'SmartTrash': {
        'format': 'M/D/YYYY',
        'label': 'Date:',
        'examples': ['1/1/2026'],
        'extract': _extract_smarttrash_date
    },
    'LRS': {
        'format': 'Mon-DD-YY',
        'label': 'Invoice Date',
        'examples': ['Dec-15-25'],
        'extract': _extract_lrs_date
    },
    'Eagle Disposal': {
        'format': 'Weekday Mon DD, YYYY',
        'label': 'inline date',
        'examples': ['Wed Oct 1, 2025'],
        'extract': _extract_eagle_disposal_date
    },
    'Fusion Waste': {
        'format': 'MM/DD/YYYY',
        'label': 'INVOICE DATE',
        'examples': ['11/30/2025'],
        'extract': _extract_fusion_waste_date
    },
    'Alaska Waste': {
        'format': 'MM/DD/YY',
        'label': 'STATEMENT DATE',
        'examples': ['03/01/25'],
        'extract': _extract_alaska_waste_date
    },
    'Papillion Sanitation': {
        'format': 'M/D/YYYY',
        'label': 'STATEMENT DATE',
        'examples': ['11/1/2025'],
        'extract': _extract_papillion_sanitation_date
    },
    'Navajo Sanitation': {
        'format': 'M/DD/YYYY',
        'label': 'receipt date',
        'examples': ['7/29/2025'],
        'extract': _extract_navajo_sanitation_date
    },
    'American Disposal': {
        'format': 'M/DD/YY',
        'label': 'Date:',
        'examples': ['8/29/25'],
        'extract': _extract_american_disposal_date
    },
    # === TRANCHE 8 (February 2026) ===
    'Lawrence Waste': {
        'format': 'MM/DD/YYYY',
        'label': 'DATE',
        'examples': ['04/01/2025'],
        'extract': _extract_lawrence_waste_date
    },
    'Murreys Disposal': {
        'format': 'MM/DD/YY',
        'label': 'STATEMENT DATE',
        'examples': ['10/01/25'],
        'extract': _extract_murreys_disposal_date
    },
    'Ware Disposal': {
        'format': 'MM/DD/YYYY',
        'label': 'Date',
        'examples': ['07/01/2025'],
        'extract': _extract_ware_disposal_date
    },
    'Capital Waste': {
        'format': 'Month DD, YYYY',
        'label': 'DATE',
        'examples': ['Jun 30, 2025'],
        'extract': _extract_capital_waste_date
    },
    'Friedman Recycling': {
        'format': 'MM/DD/YY',
        'label': 'Invoice Date',
        'examples': ['10/31/25'],
        'extract': _extract_friedman_recycling_date
    },
    'Win Waste': {
        'format': 'Mon-DD-YY',
        'label': 'DATE',
        'examples': ['Jun-01-25'],
        'extract': _extract_win_waste_date
    },
    'Novak Sanitary': {
        'format': 'M/D/YYYY',
        'label': 'STATEMENT DATE',
        'examples': ['10/1/2025'],
        'extract': _extract_novak_sanitary_date
    },
    'CR&R': {
        'format': 'MM/DD/YY',
        'label': 'Invoice Date',
        'examples': ['01/02/26'],
        'extract': _extract_crr_date
    },
    'Burrtec': {
        'format': 'MM/DD/YY',
        'label': 'Statement Date',
        'examples': ['07/31/25'],
        'extract': _extract_burrtec_date
    },
    'American Recycling': {
        'format': 'MM/DD/YY',
        'label': 'Date In',
        'examples': ['11/21/25'],
        'extract': _extract_american_recycling_date
    },
    'Homewood Disposal': {
        'format': 'MM/DD/YYYY',
        'label': 'Billing Date',
        'examples': ['12/01/2025'],
        'extract': _extract_homewood_disposal_date
    },
    'EcoSouth': {
        'format': 'MM/DD/YYYY',
        'label': 'Date',
        'examples': ['06/30/2025'],
        'extract': _extract_ecosouth_date
    },
    # === TRANCHE 9 (February 2026) ===
    'Stryker Environmental': {
        'format': 'MM/DD/YYYY',
        'label': 'Invoice date:',
        'examples': ['06/12/2025'],
        'extract': _extract_stryker_environmental_date
    },
    'Compactor Rentals of America': {
        'format': 'MM/DD/YY',
        'label': 'Invoice date',
        'examples': ['11/01/25'],
        'extract': _extract_compactor_rentals_date
    },
    'National Equipment Solutions': {
        'format': 'MM/DD/YY',
        'label': 'Date:',
        'examples': ['09/01/25'],
        'extract': _extract_national_equipment_date
    },
    'Redbox+': {
        'format': 'MM/DD/YYYY',
        'label': 'Invoice Date:',
        'examples': ['04/11/2025'],
        'extract': _extract_redbox_date
    },
    'Specific Waste': {
        'format': 'MM-DD-YYYY',
        'label': 'Date:',
        'examples': ['01-16-2025'],
        'extract': _extract_specific_waste_date
    },
    'Rocky Ridge': {
        'format': 'MM/DD/YYYY',
        'label': 'DATE',
        'examples': ['12/01/2025'],
        'extract': _extract_rocky_ridge_date
    },
    'Tower Compactor': {
        'format': 'M/D/YYYY',
        'label': 'Date',
        'examples': ['2/1/2025'],
        'extract': _extract_tower_compactor_date
    },
    'Liberty Waste': {
        'format': 'MM/DD/YYYY',
        'label': 'Date',
        'examples': ['10/01/2025'],
        'extract': _extract_liberty_waste_date
    },
    'Kimble': {
        'format': 'M/D/YYYY',
        'label': 'INVOICE DATE',
        'examples': ['2/1/2025'],
        'extract': _extract_kimble_date
    },
    'Delta Waste': {
        'format': 'Month DD, YYYY',
        'label': 'DATE',
        'examples': ['Nov 4, 2025'],
        'extract': _extract_delta_waste_date
    },
    'Howard Disposal': {
        'format': 'M/DD/YYYY',
        'label': 'Date',
        'examples': ['1/30/2025'],
        'extract': _extract_howard_disposal_date
    },
    'Idaho Falls Utilities': {
        'format': 'MM/DD/YYYY',
        'label': 'Bill Date',
        'examples': ['04/02/2025'],
        'extract': _extract_idaho_falls_date
    },
    # === TRANCHE 10 (February 2026) ===
    'CRI Curbside': {
        'format': 'M/DD/YYYY',
        'label': 'DATE',
        'examples': ['2/19/2025'],
        'extract': _extract_cri_curbside_date
    },
    'Apex Waste': {
        'format': 'Month DD, YYYY',
        'label': 'DATE',
        'examples': ['Aug 15, 2025'],
        'extract': _extract_apex_waste_date
    },
    'Metalpro': {
        'format': 'MM/DD/YYYY',
        'label': 'Credit Memo Date: / Ship Date:',
        'examples': ['08/22/2025'],
        'extract': _extract_metalpro_date
    },
    'Las Vegas Recycling': {
        'format': 'MM/DD/YYYY',
        'label': 'Invoice date:',
        'examples': ['10/06/2025'],
        'extract': _extract_las_vegas_recycling_date
    },
    'EDCO Disposal': {
        'format': 'MM/DD/YY',
        'label': 'Billing Date',
        'examples': ['06/30/25'],
        'extract': _extract_edco_disposal_date
    },
    'Interstate Waste': {
        'format': 'MM/DD/YYYY',
        'label': 'Invoice Date:',
        'examples': ['05/31/2025'],
        'extract': _extract_interstate_waste_date
    },
    'VLS Environmental': {
        'format': 'DD-Mon-YYYY',
        'label': 'Date:',
        'examples': ['01-Jul-2025'],
        'extract': _extract_vls_environmental_date
    },
    'ACES Disposal': {
        'format': 'MM/DD/YYYY',
        'label': 'Invoice Date:',
        'examples': ['05/01/2025'],
        'extract': _extract_aces_disposal_date
    },
    'County Hauling': {
        'format': 'MM/DD/YYYY',
        'label': 'DATE',
        'examples': ['04/16/2025'],
        'extract': _extract_county_hauling_date
    },
    'EL Harvey': {
        'format': 'MM/DD/YY',
        'label': 'STATEMENT DATE',
        'examples': ['12/01/25'],
        'extract': _extract_el_harvey_date
    },
    'Stevens Disposal': {
        'format': 'M/D/YYYY',
        'label': 'Invoice Date',
        'examples': ['9/1/2025'],
        'extract': _extract_stevens_disposal_date
    },
    # === TRANCHE 11 (February 2026) ===
    'Wasatch Waste': {
        'format': 'MM/DD/YYYY',
        'label': 'FROM date',
        'examples': ['06/01/2025'],
        'extract': _extract_wasatch_waste_date
    },
    'Texas Disposal': {
        'format': 'MM/DD/YYYY',
        'label': 'Date',
        'examples': ['05/01/2025'],
        'extract': _extract_texas_disposal_date
    },
    'Atlas Disposal': {
        'format': 'Mon D, YYYY',
        'label': 'Date:',
        'examples': ['Mar 1, 2025'],
        'extract': _extract_atlas_disposal_date
    },
    'Boyas Recycling': {
        'format': 'MM/DD/YYYY',
        'label': 'Invoice Date',
        'examples': ['10/01/2025'],
        'extract': _extract_boyas_recycling_date
    },
    'Nitti Sanitation': {
        'format': 'MM/DD/YYYY',
        'label': 'DATE',
        'examples': ['12/01/2025'],
        'extract': _extract_nitti_sanitation_date
    },
    'Nexus Disposal': {
        'format': 'MM/DD/YY',
        'label': 'DATE:',
        'examples': ['11/01/25'],
        'extract': _extract_nexus_disposal_date
    },
    'My Trash': {
        'format': 'MM/DD/YYYY',
        'label': 'Invoice date:',
        'examples': ['09/15/2025'],
        'extract': _extract_my_trash_date
    },
    'Mark Dunning': {
        'format': 'MM/DD/YY',
        'label': 'INV DATE',
        'examples': ['12/01/25'],
        'extract': _extract_mark_dunning_date
    },
    'Eco-Tech': {
        'format': 'M/D/YY',
        'label': 'INV DATE',
        'examples': ['5/1/25'],
        'extract': _extract_eco_tech_date
    },
    'Ace Recycling': {
        'format': 'Month DD, YYYY',
        'label': 'DATE',
        'examples': ['Dec 31, 2025'],
        'extract': _extract_ace_recycling_date
    },
    'Heavenly Trash': {
        'format': 'Weekday Mon DD, YYYY',
        'label': 'inline date',
        'examples': ['Thu Feb 20, 2025'],
        'extract': _extract_heavenly_trash_date
    },
    # === TRANCHE 12 (February 2026) ===
    'JP Mascaro': {
        'format': 'Mon-DD-YY',
        'label': 'INVOICE DATE',
        'examples': ['Oct-13-25'],
        'extract': _extract_jp_mascaro_date
    },
    'RAM Waste': {
        'format': 'M/DD/YYYY',
        'label': 'STATEMENT DATE',
        'examples': ['5/15/2025'],
        'extract': _extract_ram_waste_date
    },
    'Valley Vista': {
        'format': 'MM/DD/YY-MM/DD/YY',
        'label': 'Invoice Period',
        'examples': ['09/01/25-09/30/25'],
        'extract': _extract_valley_vista_date
    },
    'Mountain State Waste': {
        'format': 'Month DD, YYYY',
        'label': 'Date:',
        'examples': ['Apr 30, 2025'],
        'extract': _extract_mountain_state_date
    },
    'KMG Hauling': {
        'format': 'MM/DD/YYYY',
        'label': 'INVOICE DATE',
        'examples': ['12/15/2025'],
        'extract': _extract_kmg_hauling_date
    },
    'Gateway Disposal': {
        'format': 'MM/DD/YY',
        'label': 'INV DATE',
        'examples': ['06/04/25'],
        'extract': _extract_gateway_disposal_date
    },
    'Honolulu Disposal': {
        'format': 'M/DD/YY',
        'label': 'Date:',
        'examples': ['9/30/25'],
        'extract': _extract_honolulu_disposal_date
    },
    'Ankeny Sanitation': {
        'format': 'MM/DD/YYYY',
        'label': 'Invoice Date:',
        'examples': ['08/01/2025'],
        'extract': _extract_ankeny_sanitation_date
    },
    'Independent Recycling': {
        'format': 'Mon-DD-YY',
        'label': 'DATE',
        'examples': ['Feb-28-25'],
        'extract': _extract_independent_recycling_date
    },
    'Liberty Disposal': {
        'format': 'Weekday Month DD, YYYY',
        'label': 'Date:',
        'examples': ['Mon Mar 3, 2025'],
        'extract': _extract_liberty_disposal_date
    },
    # === TRANCHE 13 (February 2026) ===
    'Live Oak': {
        'format': 'M/D/YYYY',
        'label': 'INVOICE DATE',
        'examples': ['4/1/2025'],
        'extract': _extract_live_oak_date
    },
    'ZARC Recycling': {
        'format': 'M/DD/YYYY',
        'label': 'Date:',
        'examples': ['6/10/2025'],
        'extract': _extract_zarc_recycling_date
    },
    'Detroit Disposal': {
        'format': 'M/D/YY',
        'label': 'Invoice Date',
        'examples': ['5/4/25'],
        'extract': _extract_detroit_disposal_date
    },
    'All American Waste': {
        'format': 'MM/DD/YYYY',
        'label': 'INVOICE DATE:',
        'examples': ['11/01/2025'],
        'extract': _extract_all_american_waste_date
    },
    'Huntsville Hauling': {
        'format': 'MM/DD/YYYY',
        'label': 'Date',
        'examples': ['09/15/2025'],
        'extract': _extract_huntsville_hauling_date
    },
    'Amwaste': {
        'format': 'MM/DD/YYYY',
        'label': 'INVOICE DATE:',
        'examples': ['11/01/2025'],
        'extract': _extract_amwaste_date
    },
    'GHW Waste': {
        'format': 'DD-Mon-YYYY',
        'label': 'DATE',
        'examples': ['31-Jan-2025'],
        'extract': _extract_ghw_waste_date
    },
    'Grizzly Disposal': {
        'format': 'Weekday Mon DD, YYYY',
        'label': 'inline date',
        'examples': ['Wed May 21, 2025'],
        'extract': _extract_grizzly_disposal_date
    },
    'Granger Waste': {
        'format': 'MM/DD/YYYY',
        'label': 'Invoice Date:',
        'examples': ['01/31/2025'],
        'extract': _extract_granger_waste_date
    },
    # === TRANCHE 14 (February 2026) ===
    'RDT Inc': {
        'format': 'Weekday Mon DD, YYYY',
        'label': 'inline date',
        'examples': ['Tue Dec 31, 2024'],
        'extract': _extract_rdt_inc_date
    },
    'Pete & Pete': {
        'format': 'M/D/YY',
        'label': 'DATE:',
        'examples': ['6/27/25'],
        'extract': _extract_pete_pete_date
    },
    'Troiano Waste': {
        'format': 'M/D/YYYY',
        'label': 'INVOICE DATE',
        'examples': ['12/1/2025'],
        'extract': _extract_troiano_waste_date
    },
    'Western Disposal': {
        'format': 'MM-DD-YYYY',
        'label': 'Billing Date',
        'examples': ['10-01-2025'],
        'extract': _extract_western_disposal_date
    },
    'Trash Taxi': {
        'format': 'M/D/YYYY',
        'label': 'received on',
        'examples': ['10/2/2025'],
        'extract': _extract_trash_taxi_date
    },
    'Arrowaste': {
        'format': 'MM/DD/YYYY',
        'label': 'Invoice Date:',
        'examples': ['11/01/2025'],
        'extract': _extract_arrowaste_date
    },
    'Wise Environmental': {
        'format': 'Month DD, YYYY',
        'label': 'DATE',
        'examples': ['Dec 30, 2025'],
        'extract': _extract_wise_environmental_date
    },
    'NK Waste': {
        'format': 'MM/DD/YY',
        'label': 'DATE',
        'examples': ['07/31/25'],
        'extract': _extract_nk_waste_date
    },
    'Blue Diamond Disposal': {
        'format': 'Mon-DD-YY',
        'label': 'DATE',
        'examples': ['Nov-30-25'],
        'extract': _extract_blue_diamond_date
    },
    'Community Disposal': {
        'format': 'MM/DD/YYYY',
        'label': 'DATE',
        'examples': ['03/14/2025'],
        'extract': _extract_community_disposal_date
    },
    # === TRANCHE 15 (February 2026) ===
    'Basin Disposal': {
        'format': 'Month DD, YYYY',
        'label': 'BILLING DATE:',
        'examples': ['August 31, 2025'],
        'extract': _extract_basin_disposal_date
    },
    'Walker Lake Disposal': {
        'format': 'MM/DD/YYYY',
        'label': 'Invoice date:',
        'examples': ['12/01/2025'],
        'extract': _extract_walker_lake_date
    },
    'Gulf Coast Containers': {
        'format': 'Mon-DD-YY',
        'label': 'DATE',
        'examples': ['Nov-01-25'],
        'extract': _extract_gulf_coast_date
    },
    '121 Disposal': {
        'format': 'M/D/YYYY',
        'label': 'Date',
        'examples': ['7/18/2025'],
        'extract': _extract_121_disposal_date
    },
    'Patriot Waste': {
        'format': 'MM/DD/YYYY',
        'label': 'DATE',
        'examples': ['08/15/2025'],
        'extract': _extract_patriot_waste_date
    },
    'Solid Waste Authority': {
        'format': 'MM/DD/YYYY',
        'label': 'INVOICE DATE',
        'examples': ['07/31/2025'],
        'extract': _extract_solid_waste_authority_date
    },
    'Velpen Trucking': {
        'format': 'M/D/YYYY',
        'label': 'received on',
        'examples': ['11/20/2025'],
        'extract': _extract_velpen_trucking_date
    },
    'Louisiana Waste': {
        'format': 'Mon D, YYYY',
        'label': 'DATE',
        'examples': ['Apr 1, 2025'],
        'extract': _extract_louisiana_waste_date
    },
    'Renewable Resources': {
        'format': 'MM/DD/YYYY',
        'label': 'Invoice Date',
        'examples': ['04/25/2025'],
        'extract': _extract_renewable_resources_date
    },
    # === TRANCHE 16 (February 2026) ===
    'Lexington Site Services': {
        'format': 'Month DD, YYYY',
        'label': 'Billing Date',
        'examples': ['Nov 26, 2025'],
        'extract': _extract_lexington_site_date
    },
    'Modern Recycling': {
        'format': 'MM/DD/YY',
        'label': 'Date:',
        'examples': ['05/01/25'],
        'extract': _extract_modern_recycling_date
    },
    'WG Waste': {
        'format': 'MM/DD/YY',
        'label': 'INV DATE',
        'examples': ['10/01/25'],
        'extract': _extract_wg_waste_date
    },
    'Boro Wide': {
        'format': 'Month DD, YYYY',
        'label': 'Invoice Date',
        'examples': ['June 14, 2025'],
        'extract': _extract_boro_wide_date
    },
    'Moore Coal': {
        'format': 'Mon-DD-YY',
        'label': 'DATE',
        'examples': ['Oct-31-25'],
        'extract': _extract_moore_coal_date
    },
    'Curbside': {
        'format': 'Month DD, YYYY',
        'label': 'Date:',
        'examples': ['May 9, 2025'],
        'extract': _extract_curbside_date
    },
    'Redgate Disposal': {
        'format': 'M/D/YYYY',
        'label': 'Date',
        'examples': ['5/1/2025'],
        'extract': _extract_redgate_disposal_date
    },
    '1-800-Got-Junk': {
        'format': 'MM/DD/YYYY',
        'label': 'Date:',
        'examples': ['05/24/2025'],
        'extract': _extract_1800_got_junk_date
    },
    'Pelican Waste': {
        'format': 'MM/DD/YYYY',
        'label': 'Invoice Date',
        'examples': ['11/01/2024'],
        'extract': _extract_pelican_waste_date
    },
    # === TRANCHE 17 (February 2026) ===
    'Waste Away': {
        'format': 'MM/DD/YYYY',
        'label': 'Invoice Date',
        'examples': ['12/31/2024'],
        'extract': _extract_waste_away_date
    },
    'Blue Hills Environmental': {
        'format': 'Month DD, YYYY',
        'label': 'Date Issued',
        'examples': ['Jul 1, 2025'],
        'extract': _extract_blue_hills_date
    },
    'JLT Trucking': {
        'format': 'Month DD, YYYY',
        'label': 'DATE',
        'examples': ['Jul 1, 2025'],
        'extract': _extract_jlt_trucking_date
    },
    'SSW Frontload': {
        'format': 'Weekday Mon DD, YYYY',
        'label': 'received on',
        'examples': ['Thu Feb 20, 2025'],
        'extract': _extract_ssw_frontload_date
    },
    'Ace Waste Systems': {
        'format': 'MM/DD/YYYY',
        'label': 'Invoice Date:',
        'examples': ['01/09/2025'],
        'extract': _extract_ace_waste_systems_date
    },
    'Stericycle': {
        'format': 'MM-DD-YYYY',
        'label': 'Invoice Date',
        'examples': ['06-18-2025'],
        'extract': _extract_stericycle_date
    },
    'Trident Waste': {
        'format': 'MM/DD/YYYY',
        'label': 'Date',
        'examples': ['08/08/2025'],
        'extract': _extract_trident_waste_date
    },
    'ABC Waste': {
        'format': 'MM/DD/YYYY',
        'label': 'Date',
        'examples': ['01/01/2026'],
        'extract': _extract_abc_waste_date
    },
    'Cards Mo': {
        'format': 'MM/DD/YYYY',
        'label': 'Date',
        'examples': ['01/12/2026'],
        'extract': _extract_cards_mo_date
    },
    'West Central Sanitation': {
        'format': 'MM/DD/YYYY',
        'label': 'Billing Date',
        'examples': ['12/01/2025'],
        'extract': _extract_west_central_date
    },
    # === TRANCHE 18 (February 2026) ===
    'City Waste': {
        'format': 'MM/DD/YYYY',
        'label': 'Invoice Date:',
        'examples': ['11/13/2025'],
        'extract': _extract_city_waste_date
    },
    'CWPM': {
        'format': 'MM/DD/YY',
        'label': 'Invoice Date',
        'examples': ['11/30/25'],
        'extract': _extract_cwpm_date
    },
    'Roll Off Systems': {
        'format': 'MM/DD/YYYY',
        'label': 'Invoice Date',
        'examples': ['07/01/2025'],
        'extract': _extract_roll_off_systems_date
    },
    'TK Trash': {
        'format': 'MM/DD/YYYY',
        'label': 'Billing Date:',
        'examples': ['06/01/2025'],
        'extract': _extract_tk_trash_date
    },
    'Corporate Services Consultants': {
        'format': 'M/D/YYYY',
        'label': 'Date',
        'examples': ['12/1/2025'],
        'extract': _extract_corporate_services_date
    },
    'ABC Disposal Systems': {
        'format': 'MM/DD/YYYY',
        'label': 'Date',
        'examples': ['09/01/2025'],
        'extract': _extract_abc_disposal_systems_date
    },
    'Vogel Disposal': {
        'format': 'MM/DD/YYYY',
        'label': 'Invoice Date:',
        'examples': ['07/01/2025'],
        'extract': _extract_vogel_disposal_date
    },
    'AAA Disposal Service': {
        'format': 'M/DD/YY',
        'label': 'inline date',
        'examples': ['4/01/25'],
        'extract': _extract_aaa_disposal_service_date
    },
    'City of Tucson': {
        'format': 'MM/DD/YY',
        'label': 'Bill Date',
        'examples': ['11/14/25'],
        'extract': _extract_city_of_tucson_date
    },
    'Becker360': {
        'format': 'Month DD, YYYY',
        'label': 'Document Date',
        'examples': ['June 23, 2025'],
        'extract': _extract_becker360_date
    },
    # === TRANCHE 19 (February 2026) ===
    'Clean Slate': {
        'format': 'Month DD, YYYY',
        'label': 'Payment Date:',
        'examples': ['Dec 10, 2025'],
        'extract': _extract_clean_slate_date
    },
    'Wall Recycling': {
        'format': 'MM/DD/YYYY',
        'label': 'Date',
        'examples': ['03/31/2025'],
        'extract': _extract_wall_recycling_date
    },
    'Total Reclaim': {
        'format': 'MM/DD/YY',
        'label': 'Invoice Date:',
        'examples': ['01/31/25'],
        'extract': _extract_total_reclaim_date
    },
    'Dependable Sanitation': {
        'format': 'MM/DD/YYYY',
        'label': 'received on',
        'examples': ['10/22/2025'],
        'extract': _extract_dependable_sanitation_date
    },
    'EOMS Recycling': {
        'format': 'Weekday Mon DD, YYYY',
        'label': 'Invoice date',
        'examples': ['Thu Jul 31, 2025'],
        'extract': _extract_eoms_recycling_date
    },
    'Kahut Waste': {
        'format': 'M/D/YYYY',
        'label': 'STATEMENT DATE',
        'examples': ['2/1/2025'],
        'extract': _extract_kahut_waste_date
    },
    'Modern Corporation': {
        'format': 'MM/DD/YY',
        'label': 'Date:',
        'examples': ['04/01/25'],
        'extract': _extract_modern_corporation_date
    },
    'Ohio Valley Waste': {
        'format': 'MM/DD/YYYY',
        'label': 'Invoice Date:',
        'examples': ['11/01/2025'],
        'extract': _extract_ohio_valley_waste_date
    },
    'Specialty Pallet': {
        'format': 'M/D/YYYY',
        'label': 'Order Date',
        'examples': ['6/4/2025'],
        'extract': _extract_specialty_pallet_date
    },
    # === TRANCHE 20 (February 2026) ===
    'Pennohio': {
        'format': 'M/D/YYYY',
        'label': 'INVOICE DATE',
        'examples': ['5/1/2025'],
        'extract': _extract_pennohio_date
    },
    'West Oahu Aggregate': {
        'format': 'MM/DD/YYYY',
        'label': 'Invoice date:',
        'examples': ['01/01/2025'],
        'extract': _extract_west_oahu_aggregate_date
    },
    'Heiberg Garbage': {
        'format': 'MM/DD/YY',
        'label': 'Closing Date',
        'examples': ['10/26/25'],
        'extract': _extract_heiberg_garbage_date
    },
    'County Waste Systems': {
        'format': 'MM/DD/YYYY',
        'label': 'Date',
        'examples': ['01/01/2026'],
        'extract': _extract_county_waste_systems_date
    },
    'Grace Hauling': {
        'format': 'MM/DD/YYYY',
        'label': 'INVOICE DATE',
        'examples': ['03/01/2025'],
        'extract': _extract_grace_hauling_date
    },
    'D Crescio Trucking': {
        'format': 'Month D, YYYY',
        'label': 'Date',
        'examples': ['Nov 1, 2025'],
        'extract': _extract_d_crescio_trucking_date
    },
    'Direct Waste Services': {
        'format': 'Month D, YYYY',
        'label': 'INVOICE DATE',
        'examples': ['Jul 1, 2025'],
        'extract': _extract_direct_waste_services_date
    },
    'J&K Trash': {
        'format': 'MM/DD/YY',
        'label': 'INV DATE',
        'examples': ['09/15/25'],
        'extract': _extract_jk_trash_date
    },
    'Junk Removed Now': {
        'format': 'Weekday Mon DD, YYYY',
        'label': 'Date',
        'examples': ['Fri May 09, 2025'],
        'extract': _extract_junk_removed_now_date
    },
    'Atlantic Waste': {
        'format': 'M/DD/YY',
        'label': 'Invoice Date',
        'examples': ['7/31/25'],
        'extract': _extract_atlantic_waste_date
    },
    'Hill Country Waste': {
        'format': 'MM/DD/YYYY',
        'label': 'received on',
        'examples': ['7/28/2025'],
        'extract': _extract_hill_country_waste_date
    },
    'Florida Express Waste': {
        'format': 'MM/DD/YYYY',
        'label': 'Statement Date',
        'examples': ['05/31/2025'],
        'extract': _extract_florida_express_waste_date
    },
    'Community Waste': {
        'format': 'MM/DD/YYYY',
        'label': 'Invoice Date',
        'examples': ['12/01/2025'],
        'extract': _extract_community_waste_date
    },
    # === TRANCHE 21 (February 2026) ===
    'Chrin Hauling': {
        'format': 'Month D, YYYY',
        'label': 'INVOICE DATE',
        'examples': ['Sep 26, 2025'],
        'extract': _extract_chrin_hauling_date
    },
    'Western Elite': {
        'format': 'Month DD, YYYY',
        'label': 'Statement',
        'examples': ['June 30, 2025'],
        'extract': _extract_western_elite_date
    },
    'WillScot': {
        'format': 'M/D/YYYY',
        'label': 'Invoice Date',
        'examples': ['5/9/2025'],
        'extract': _extract_willscot_date
    },
    'Ryland Environmental': {
        'format': 'DD-Mon-YYYY',
        'label': 'Date:',
        'examples': ['24-Nov-2025'],
        'extract': _extract_ryland_environmental_date
    },
    'Penn Waste': {
        'format': 'M/D/YYYY',
        'label': 'Date:',
        'examples': ['9/30/2025'],
        'extract': _extract_penn_waste_date
    },
    'Thompson Sanitation': {
        'format': 'MM/DD/YYYY',
        'label': 'received on',
        'examples': ['12/5/2025'],
        'extract': _extract_thompson_sanitation_date
    },
    'Five Star Waste': {
        'format': 'MM/DD/YYYY',
        'label': 'DATE',
        'examples': ['11/24/2025'],
        'extract': _extract_five_star_waste_date
    },
    'Pellitteri': {
        'format': 'Weekday, Month DD, YYYY',
        'label': 'Statement date',
        'examples': ['Tuesday, July 15, 2025'],
        'extract': _extract_pellitteri_date
    },
    'Great Waste': {
        'format': 'M/DD/YY',
        'label': 'Invoice Date',
        'examples': ['7/15/25'],
        'extract': _extract_great_waste_date
    },
    'City of Fargo': {
        'format': 'M/DD/YY',
        'label': 'DATE:',
        'examples': ['4/02/25'],
        'extract': _extract_city_of_fargo_date
    },
    # === TRANCHE 22 (February 2026) ===
    'Cards Recycling': {
        'format': 'MM/DD/YYYY',
        'label': 'Date',
        'examples': ['12/10/2025'],
        'extract': _extract_cards_recycling_date
    },
    'DeKalb County': {
        'format': 'MM/DD/YY',
        'label': 'Bill Date:',
        'examples': ['04/07/25'],
        'extract': _extract_dekalb_county_date
    },
    "Sonny's Solid Waste": {
        'format': 'Weekday Mon DD, YYYY',
        'label': 'Date:',
        'examples': ['Tue Mar 25, 2025'],
        'extract': _extract_sonnys_solid_waste_date
    },
    'Waste Services LLC': {
        'format': 'M/D/YYYY',
        'label': 'Invoice Date',
        'examples': ['1/5/2026'],
        'extract': _extract_waste_services_llc_date
    },
    'Southern Sanitation': {
        'format': 'MM/DD/YYYY',
        'label': 'DATE',
        'examples': ['12/01/2025'],
        'extract': _extract_southern_sanitation_date
    },
    'Greif': {
        'format': 'MM-DD-YYYY',
        'label': 'Transfer Date',
        'examples': ['07-29-2025'],
        'extract': _extract_greif_date
    },
    'Orlando Waste Paper': {
        'format': 'MM/DD/YY',
        'label': 'INV DATE',
        'examples': ['01/31/25'],
        'extract': _extract_orlando_waste_paper_date
    },
    'Gotta Go Waste': {
        'format': 'MM/DD/YYYY',
        'label': 'Date',
        'examples': ['01/15/2025'],
        'extract': _extract_gotta_go_waste_date
    },
    # === TRANCHE 23 (February 2026) ===
    'TFC Recycling': {
        'format': 'M/D/YYYY',
        'label': 'Date',
        'examples': ['3/1/2025'],
        'extract': _extract_tfc_recycling_date
    },
    'Premier Waste': {
        'format': 'MM/DD/YY',
        'label': 'STATEMENT DATE',
        'examples': ['07/25/25'],
        'extract': _extract_premier_waste_date
    },
    'Richardson Waste': {
        'format': 'MM/DD/YYYY',
        'label': 'Date',
        'examples': ['11/24/2025'],
        'extract': _extract_richardson_waste_date
    },
    'Waste Path': {
        'format': 'MM/DD/YYYY',
        'label': 'DATE',
        'examples': ['10/02/2025'],
        'extract': _extract_waste_path_date
    },
    'Indiana Waste': {
        'format': 'MM/DD/YY',
        'label': 'INV DATE',
        'examples': ['07/01/25'],
        'extract': _extract_indiana_waste_date
    },
    'City of Jackson': {
        'format': 'MM/DD/YYYY',
        'label': 'BILL DATE',
        'examples': ['09/17/2025'],
        'extract': _extract_city_of_jackson_date
    },
    'Green Guys': {
        'format': 'DD Mon YYYY',
        'label': 'Payment Date',
        'examples': ['04 Dec 2025'],
        'extract': _extract_green_guys_date
    },
    'Texas Pride Disposal': {
        'format': 'MM/DD/YYYY',
        'label': 'Invoice Date',
        'examples': ['12/10/2025'],
        'extract': _extract_texas_pride_disposal_date
    },
    'All Metals Recycling': {
        'format': 'M/DD/YYYY',
        'label': 'Date',
        'examples': ['5/26/2025'],
        'extract': _extract_all_metals_recycling_date
    },
    'Advance Machine & Hydraulic': {
        'format': 'MM/DD/YYYY',
        'label': 'Invoice date:',
        'examples': ['10/21/2025'],
        'extract': _extract_advance_machine_date
    },
    'City of Blackfoot': {
        'format': 'MM/DD/YY',
        'label': 'DUE DATE',
        'examples': ['01/14/26'],
        'extract': _extract_city_of_blackfoot_date
    },
    'City of Boise': {
        'format': 'MM/DD/YYYY',
        'label': 'Statement Date:',
        'examples': ['07/01/2025'],
        'extract': _extract_city_of_boise_date
    },
    # === TRANCHE 24 (February 2026) ===
    'Circle Sanitation': {
        'format': 'M/D/YYYY',
        'label': 'Date',
        'examples': ['6/20/2025'],
        'extract': _extract_circle_sanitation_date
    },
    'Uribe Refuse': {
        'format': 'MM/DD/YYYY',
        'label': 'DATE',
        'examples': ['01/31/2025'],
        'extract': _extract_uribe_refuse_date
    },
    'Conex Recycling': {
        'format': 'M/D/YYYY',
        'label': 'DATE',
        'examples': ['2/1/2025'],
        'extract': _extract_conex_recycling_date
    },
    'Roosevelt UT': {
        'format': 'MM/DD/YYYY',
        'label': 'BILLING DATE',
        'examples': ['03/31/2025'],
        'extract': _extract_roosevelt_ut_date
    },
    'Cleeton Sanitation': {
        'format': 'Month YYYY',
        'label': 'BILLING PERIOD',
        'examples': ['OCTOBER, 2025'],
        'extract': _extract_cleeton_sanitation_date
    },
    'Intermountain Disposal': {
        'format': 'M/D/YYYY',
        'label': 'Date',
        'examples': ['6/30/2025'],
        'extract': _extract_intermountain_disposal_date
    },
    'AG Logistics': {
        'format': 'MM/DD/YYYY',
        'label': 'DATE',
        'examples': ['07/30/2025'],
        'extract': _extract_ag_logistics_date
    },
    'PRIDE Disposal': {
        'format': 'MM/DD/YYYY',
        'label': 'INV. DATE',
        'examples': ['04/30/2025'],
        'extract': _extract_pride_disposal_date
    },
    'Cavossa Disposal': {
        'format': 'MM/DD/YYYY',
        'label': 'ACCOUNT SUMMARY AS OF',
        'examples': ['10/01/2025'],
        'extract': _extract_cavossa_disposal_date
    },
    'Royal Document Destruction': {
        'format': 'MM/DD/YYYY',
        'label': 'Services through',
        'examples': ['10/31/2025'],
        'extract': _extract_royal_document_date
    },
    'Lawrence County Solid Waste': {
        'format': 'MM/DD/YYYY',
        'label': 'Invoice Date:',
        'examples': ['05/31/2025'],
        'extract': _extract_lawrence_county_date
    },
    'Bruin Waste Management': {
        'format': 'Month DD, YYYY',
        'label': 'INVOICE DATE',
        'examples': ['Jul 31, 2025'],
        'extract': _extract_bruin_waste_date
    },
    # === TRANCHE 25 (February 2026) ===
    'City of Meridian': {
        'format': 'MM/DD/YYYY',
        'label': 'Date: (inline)',
        'examples': ['10/05/2025'],
        'extract': _extract_city_of_meridian_date
    },
    'Black Hawk Waste': {
        'format': 'MM/DD/YYYY',
        'label': 'Date',
        'examples': ['11/01/2025'],
        'extract': _extract_black_hawk_waste_date
    },
    'CRP Sanitation': {
        'format': 'Mon-DD-YY',
        'label': 'DATE',
        'examples': ['Sep-27-25'],
        'extract': _extract_crp_sanitation_date
    },
    'Salandro Refuse': {
        'format': 'MM/DD/YYYY',
        'label': 'Invoice Date',
        'examples': ['12/01/2025'],
        'extract': _extract_salandro_refuse_date
    },
    'City of Deerfield Beach': {
        'format': 'MM/DD/YYYY',
        'label': 'DATE',
        'examples': ['01/15/2025'],
        'extract': _extract_city_of_deerfield_beach_date
    },
    'Olympic Compactor Rentals': {
        'format': 'M/D/YYYY',
        'label': 'INVOICE DATE:',
        'examples': ['1/15/2025'],
        'extract': _extract_olympic_compactor_date
    },
    'Dunham': {
        'format': 'MM/DD/YYYY',
        'label': 'Invoice Date:',
        'examples': ['01/15/2025'],
        'extract': _extract_dunham_date
    },
    'City of Nampa': {
        'format': 'M/DD/YYYY',
        'label': 'Statement Date',
        'examples': ['1/15/2025'],
        'extract': _extract_city_of_nampa_date
    },
    'Pascon': {
        'format': 'MM/DD/YYYY',
        'label': 'Date',
        'examples': ['01/02/2025'],
        'extract': _extract_pascon_date
    },
    'Rockwood Sustainable Solutions': {
        'format': 'Mon-DD-YY',
        'label': 'DATE (reverse columnar)',
        'examples': ['Sep-27-25'],
        'extract': _extract_rockwood_sustainable_date
    },
    'J&T Environmental': {
        'format': 'M/D/YYYY',
        'label': 'Date',
        'examples': ['1/15/2025'],
        'extract': _extract_jt_environmental_date
    },
    'Cooks Wastepaper': {
        'format': 'MM/DD/YY',
        'label': 'STATEMENT DATE',
        'examples': ['01/15/25'],
        'extract': _extract_cooks_wastepaper_date
    },
    'Southern Illinois Waste': {
        'format': 'M/D/YYYY',
        'label': 'Date',
        'examples': ['1/15/2025'],
        'extract': _extract_southern_illinois_waste_date
    },
    'Geodom Carting': {
        'format': 'MM/DD/YYYY',
        'label': 'DATE',
        'examples': ['01/15/2025'],
        'extract': _extract_geodom_carting_date
    },
    'G2 Revolution': {
        'format': 'MM/DD/YYYY',
        'label': 'Invoice date:',
        'examples': ['01/15/2025'],
        'extract': _extract_g2_revolution_date
    },
    'All Florida Scrap Metals': {
        'format': 'MM/DD/YYYY',
        'label': 'Invoice Date',
        'examples': ['01/15/2025'],
        'extract': _extract_all_florida_scrap_metals_date
    },
    'Jettison Environmental': {
        'format': 'MM/DD/YYYY',
        'label': 'INVOICE DATE',
        'examples': ['01/15/2025'],
        'extract': _extract_jettison_environmental_date
    },
    'UDP TN Hauling': {
        'format': 'MM/DD/YYYY',
        'label': 'INVOICE DATE (reverse columnar)',
        'examples': ['01/15/2025'],
        'extract': _extract_udp_tn_hauling_date
    },
    'The Trash Man': {
        'format': 'Weekday Month DD, YYYY',
        'label': 'TrashBilling format',
        'examples': ['Thu May 1, 2025'],
        'extract': _extract_the_trash_man_date
    },
    'Tri-City Disposal': {
        'format': 'Weekday Month DD, YYYY',
        'label': 'TrashBilling format',
        'examples': ['Thu May 15, 2025'],
        'extract': _extract_tri_city_disposal_date
    },
    'Hoss Disposal': {
        'format': 'MM/DD/YY',
        'label': 'early lines',
        'examples': ['09/25/25'],
        'extract': _extract_hoss_disposal_date
    },
    'AM Disposal': {
        'format': 'Month DD, YYYY',
        'label': 'Issue date',
        'examples': ['May 1, 2025'],
        'extract': _extract_am_disposal_date
    },
    'Northern Waste': {
        'format': 'MM/DD/YYYY',
        'label': 'INVOICE DATE',
        'examples': ['12/31/2025'],
        'extract': _extract_northern_waste_date
    },
    "Burgmeier's Hauling": {
        'format': 'MM/DD/YY',
        'label': 'INV DATE',
        'examples': ['12/31/25'],
        'extract': _extract_burgmeiers_hauling_date
    },
    'Sunrise Sanitation Service': {
        'format': 'M/D/YYYY',
        'label': 'Date',
        'examples': ['4/30/2025'],
        'extract': _extract_sunrise_sanitation_service_date
    },
    'C & D Disposal': {
        'format': 'MM/DD/YY',
        'label': 'Invoice Date',
        'examples': ['04/01/25'],
        'extract': _extract_c_d_disposal_date
    },
    'First Piedmont': {
        'format': 'M/DD/YY',
        'label': 'INVOICE DATE:',
        'examples': ['7/31/25'],
        'extract': _extract_first_piedmont_date
    },
    # === TRANCHE 26 (February 2026) ===
    'Mid Valley Disposal': {
        'format': 'M/DD/YY',
        'label': 'Invoice Date',
        'examples': ['9/30/25'],
        'extract': _extract_mid_valley_disposal_date
    },
    'Kootenai County Solid Waste': {
        'format': 'MM/DD/YYYY',
        'label': 'Bill Date:',
        'examples': ['02/14/2025'],
        'extract': _extract_kootenai_county_date
    },
    'BCC Waste Solutions': {
        'format': 'M/D/YYYY',
        'label': 'INVOICE DATE',
        'examples': ['5/2/2025'],
        'extract': _extract_bcc_waste_date
    },
    'Schaap Sanitation': {
        'format': 'M/D/YYYY',
        'label': 'STATEMENT DATE',
        'examples': ['10/1/2025'],
        'extract': _extract_schaap_sanitation_date
    },
    'Amber Disposal': {
        'format': 'MM/DD/YY',
        'label': 'INV DATE',
        'examples': ['03/25/25'],
        'extract': _extract_amber_disposal_date
    },
    'Appalachian Waste Management': {
        'format': 'MM/DD/YYYY',
        'label': 'INVOICE DATE (reverse columnar)',
        'examples': ['02/28/2025'],
        'extract': _extract_appalachian_waste_date
    },
    'F & L Construction': {
        'format': 'DD-Mon-YYYY',
        'label': 'DATE',
        'examples': ['01-Mar-2025'],
        'extract': _extract_f_l_construction_date
    },
    'Vista Recycling': {
        'format': 'M/D/YY',
        'label': 'Invoice Date',
        'examples': ['8/1/25'],
        'extract': _extract_vista_recycling_date
    },
    'Martin Environmental': {
        'format': 'MM/DD/YYYY',
        'label': 'Invoice Date',
        'examples': ['09/01/2025'],
        'extract': _extract_martin_environmental_date
    },
    'Rich County': {
        'format': 'MM/DD/YYYY',
        'label': 'Date',
        'examples': ['01/01/2026'],
        'extract': _extract_rich_county_date
    },
    'Pop and Son Trucking': {
        'format': 'Month DD, YYYY',
        'label': 'Issue date',
        'examples': ['Apr 1, 2025'],
        'extract': _extract_pop_and_son_date
    },
    'AT Disposal': {
        'format': 'MM/DD/YYYY',
        'label': 'Date',
        'examples': ['09/01/2025'],
        'extract': _extract_at_disposal_date
    },
    'Waste Pro Oregon': {
        'format': 'Month DD, YYYY',
        'label': 'BILL DATE:',
        'examples': ['December 31, 2024'],
        'extract': _extract_waste_pro_oregon_date
    },
    'Mission Trail Waste': {
        'format': 'M/DD/YYYY',
        'label': 'INV. DATE',
        'examples': ['8/31/2025'],
        'extract': _extract_mission_trail_date
    },
    'Hart Sanitation': {
        'format': 'M/DD/YYYY',
        'label': 'received on (TrashBilling)',
        'examples': ['7/28/2025'],
        'extract': _extract_hart_sanitation_date
    },
    'Disposal Services LLC': {
        'format': 'M/DD/YYYY',
        'label': 'received on (TrashBilling)',
        'examples': ['6/18/2025'],
        'extract': _extract_disposal_services_llc_date
    },
    'Ozark Disposal': {
        'format': 'M/DD/YYYY',
        'label': 'received on (TrashBilling)',
        'examples': ['8/29/2025'],
        'extract': _extract_ozark_disposal_date
    },
    "Marick's Waste Disposal": {
        'format': 'M/DD/YYYY',
        'label': 'received on (TrashBilling)',
        'examples': ['10/15/2025'],
        'extract': _extract_maricks_waste_date
    },
    'City of Bardstown': {
        'format': 'DD Mon YYYY',
        'label': 'ISSUED ON',
        'examples': ['26 Nov 2025'],
        'extract': _extract_city_of_bardstown_date
    },
    # === TRANCHE 27 (February 2026) ===
    'Garden Isle Disposal': {
        'format': 'MM/DD/YYYY',
        'label': 'DATE',
        'examples': ['10/25/2025'],
        'extract': _extract_garden_isle_disposal_date
    },
    'Ontario Municipal': {
        'format': 'M/D/YYYY',
        'label': 'Bill Date:',
        'examples': ['10/9/2025'],
        'extract': _extract_ontario_municipal_date
    },
    'Allstate Equipment Services': {
        'format': 'MM/DD/YYYY',
        'label': 'DATE',
        'examples': ['01/23/2025'],
        'extract': _extract_allstate_equipment_date
    },
    'Pete and Pete': {
        'format': 'MM/DD/YYYY',
        'label': 'INVOICE DATE',
        'examples': ['01/15/2025'],
        'extract': _extract_pete_and_pete_date
    },
    'Quality Waste': {
        'format': 'DD-Mon-YYYY',
        'label': 'DATE',
        'examples': ['30-Jun-2025'],
        'extract': _extract_quality_waste_date
    },
    'Reliable Sanitation': {
        'format': 'M/DD/YYYY',
        'label': 'received on (TrashBilling)',
        'examples': ['3/28/2025'],
        'extract': _extract_reliable_sanitation_date
    },
    'Grogan Waste': {
        'format': 'MM/DD/YYYY',
        'label': 'DATE (inline)',
        'examples': ['03/01/2025'],
        'extract': _extract_grogan_waste_date
    },
    'Efficient Roll-Off & Recycling': {
        'format': 'M/DD/YYYY',
        'label': 'Date',
        'examples': ['9/30/2025'],
        'extract': _extract_efficient_rolloff_date
    },
    'Sanitary Service Company': {
        'format': 'M/D/YY',
        'label': 'Billing Date:',
        'examples': ['12/2/25'],
        'extract': _extract_sanitary_service_company_date
    },
    'Miami-Dade DSWM': {
        'format': 'M/DD/YY',
        'label': 'Invoice Date',
        'examples': ['8/31/25'],
        'extract': _extract_miami_dade_dswm_date
    },
    'BP Trucking': {
        'format': 'Mon-DD-YY',
        'label': 'INVOICE DATE',
        'examples': ['Jul-01-25'],
        'extract': _extract_bp_trucking_date
    },
    'Kern County Public Works': {
        'format': 'MM/DD/YYYY',
        'label': 'INVOICE DATE:',
        'examples': ['04/14/2025'],
        'extract': _extract_kern_county_date
    },
    # === TRANCHE 28 (February 2026) ===
    'L&L Site Services': {
        'format': 'Weekday Month DD, YYYY',
        'label': 'TrashBilling format',
        'examples': ['Fri Aug 22, 2025'],
        'extract': _extract_ll_site_services_date
    },
    'Earthwise Waste Solutions': {
        'format': 'Weekday Month DD, YYYY',
        'label': 'TrashBilling format',
        'examples': ['Mon Sep 1, 2025'],
        'extract': _extract_earthwise_waste_date
    },
    'Island Disposal': {
        'format': 'MM/DD/YYYY',
        'label': 'Invoice date:',
        'examples': ['09/01/2025'],
        'extract': _extract_island_disposal_date
    },
    'Lusk Disposal': {
        'format': 'MM/DD/YYYY',
        'label': 'DATE',
        'examples': ['11/26/2025'],
        'extract': _extract_lusk_disposal_date
    },
    'Pro Waste Services': {
        'format': 'MM/DD/YYYY',
        'label': 'Invoice Date',
        'examples': ['10/01/2025'],
        'extract': _extract_pro_waste_services_date
    },
    'Major Waste': {
        'format': 'MM/DD/YYYY',
        'label': 'Payment date',
        'examples': ['05/01/2025'],
        'extract': _extract_major_waste_date
    },
    "Art's Garbage": {
        'format': 'MM/DD/YY',
        'label': 'STATEMENT DATE',
        'examples': ['10/01/25'],
        'extract': _extract_arts_garbage_date
    },
    'Midwest Sanitation': {
        'format': 'M/D/YY',
        'label': 'after Billing Acct No',
        'examples': ['3/3/25'],
        'extract': _extract_midwest_sanitation_date
    },
    'Hometown Sanitation': {
        'format': 'Mon-DD-YY',
        'label': 'Date',
        'examples': ['Jan-01-26'],
        'extract': _extract_hometown_sanitation_date
    },
    'Marborg': {
        'format': 'MM/DD/YYYY',
        'label': 'Invoice Date',
        'examples': ['08/31/2025'],
        'extract': _extract_marborg_date
    },
    'Sage Disposal': {
        'format': 'Month DD, YYYY',
        'label': 'Date:',
        'examples': ['Apr 2, 2025'],
        'extract': _extract_sage_disposal_date
    },
    'Mid South Waste': {
        'format': 'MM-DD-YY',
        'label': 'early lines',
        'examples': ['10-31-25'],
        'extract': _extract_mid_south_waste_date
    },
    'LK Specialties': {
        'format': 'M/D/YYYY',
        'label': 'Date',
        'examples': ['12/9/2025'],
        'extract': _extract_lk_specialties_date
    },
    'Complete Solutions & Sourcing': {
        'format': 'M/D/YYYY',
        'label': 'Date',
        'examples': ['1/1/2025'],
        'extract': _extract_complete_solutions_date
    },
    'City of Pembroke Pines': {
        'format': 'MM/DD/YYYY',
        'label': 'BILL DATE',
        'examples': ['01/15/2025'],
        'extract': _extract_city_of_pembroke_pines_date
    },
    # === TRANCHE 29 (February 2026) ===
    'RAD Curbside': {
        'format': 'MM/DD/YYYY',
        'label': 'Payment date',
        'examples': ['06/20/2025'],
        'extract': _extract_rad_curbside_date
    },
    'American Waste Control': {
        'format': 'Month DD, YYYY',
        'label': 'INVOICE DATE',
        'examples': ['Dec 30, 2025'],
        'extract': _extract_american_waste_control_date
    },
    'Absolute Waste': {
        'format': 'MM/DD/YYYY',
        'label': 'Invoice Date:',
        'examples': ['10/01/2025'],
        'extract': _extract_absolute_waste_date
    },
    'Pak Rite Rentals': {
        'format': 'MM/DD/YYYY',
        'label': 'Invoice date',
        'examples': ['01/15/2025'],
        'extract': _extract_pak_rite_rentals_date
    },
    'Bliss Environmental': {
        'format': 'Weekday Month DD, YYYY',
        'label': 'TrashBilling format',
        'examples': ['Fri Feb 28, 2025'],
        'extract': _extract_bliss_environmental_date
    },
    'South Tahoe Refuse': {
        'format': 'MM/DD/YYYY',
        'label': 'Statement Date',
        'examples': ['07/01/2025'],
        'extract': _extract_south_tahoe_refuse_date
    },
    'Haul Away Rubbish': {
        'format': 'MM/DD/YY',
        'label': 'INV DATE',
        'examples': ['10/31/25'],
        'extract': _extract_haul_away_rubbish_date
    },
    'TRASHCO': {
        'format': 'MM/DD/YYYY',
        'label': 'Invoice Date:',
        'examples': ['07/31/2025'],
        'extract': _extract_trashco_date
    },
    'Green OBKY': {
        'format': 'MM/DD/YYYY',
        'label': 'DATE (inline)',
        'examples': ['03/01/2025'],
        'extract': _extract_green_obky_date
    },
    'CSD Disposal': {
        'format': 'MM/DD/YY',
        'label': 'Invoice Date',
        'examples': ['09/01/25'],
        'extract': _extract_csd_disposal_date
    },
    'Rapid Removal': {
        'format': 'Weekday Month DD, YYYY',
        'label': 'TrashBilling format',
        'examples': ['Tue Oct 7, 2025'],
        'extract': _extract_rapid_removal_date
    },
    'Cram-A-Lot': {
        'format': 'MM/DD/YY',
        'label': 'Invoice Date:',
        'examples': ['02/06/25'],
        'extract': _extract_cram_a_lot_date
    },
    # --- Tranche 30 ---
    'Grand Rapids Iron': {
        'format': 'MM/DD/YYYY',
        'label': 'Invoice Date:',
        'examples': ['11/06/2025'],
        'extract': _extract_grand_rapids_iron_date
    },
    'Cards KS': {
        'format': 'MM/DD/YYYY',
        'label': 'Date (columnar)',
        'examples': ['11/01/2025'],
        'extract': _extract_cards_ks_date
    },
    'Diamond Disposal': {
        'format': 'MM/DD/YYYY',
        'label': 'Invoice date:',
        'examples': ['12/01/2025'],
        'extract': _extract_diamond_disposal_date
    },
    'Trash Control': {
        'format': 'Month DD, YYYY',
        'label': 'Invoice Date:',
        'examples': ['November 01, 2025'],
        'extract': _extract_trash_control_date
    },
    'Engebretson & Sons': {
        'format': 'MM/DD/YY',
        'label': 'STATEMENT DATE',
        'examples': ['11/30/25'],
        'extract': _extract_engebretson_sons_date
    },
    'K-Town Disposal': {
        'format': 'Month DD, YYYY',
        'label': 'INVOICE DATE',
        'examples': ['October 01, 2025'],
        'extract': _extract_k_town_disposal_date
    },
    'Basin Haulage': {
        'format': 'Month DD, YYYY',
        'label': 'Invoice Date:',
        'examples': ['September 08, 2025'],
        'extract': _extract_basin_haulage_date
    },
    'Suburban Waste Services': {
        'format': 'Mon-DD-YY',
        'label': 'INVOICE DATE (reverse columnar)',
        'examples': ['Nov-01-25'],
        'extract': _extract_suburban_waste_services_date
    },
    'A-1 Disposal': {
        'format': 'M/DD/YYYY',
        'label': 'Date (columnar)',
        'examples': ['9/01/2025'],
        'extract': _extract_a1_disposal_date
    },
    'Advance Disposal': {
        'format': 'MM/DD/YYYY',
        'label': 'Invoice date:',
        'examples': ['07/01/2025'],
        'extract': _extract_advance_disposal_date
    },
    'NS Disposal': {
        'format': 'Month DD, YYYY',
        'label': 'Invoice Date:',
        'examples': ['September 01, 2025'],
        'extract': _extract_ns_disposal_date
    },
    'McGree Trucking': {
        'format': 'MM/DD/YYYY',
        'label': 'Date (columnar)',
        'examples': ['09/01/2025'],
        'extract': _extract_mcgree_trucking_date
    },
    'Updike Industries': {
        'format': 'MM/DD/YYYY',
        'label': 'Date (columnar)',
        'examples': ['09/01/2025'],
        'extract': _extract_updike_industries_date
    },
    'Green Planet 21': {
        'format': 'Month DD, YYYY',
        'label': 'Date standalone',
        'examples': ['October 1, 2025'],
        'extract': _extract_green_planet_21_date
    },
    # --- Tranche 31 ---
    'Pacific Waste': {
        'format': 'MM/DD/YYYY',
        'label': 'Total Due By (columnar)',
        'examples': ['05/31/2025'],
        'extract': _extract_pacific_waste_date
    },
    'River Parish Disposal': {
        'format': 'MM/DD/YYYY',
        'label': 'DATE(MM/DD/YYYY)',
        'examples': ['03/28/2025'],
        'extract': _extract_river_parish_disposal_date
    },
    "Mike's Rubbish": {
        'format': 'Weekday Month DD, YYYY',
        'label': 'Date: (TrashBilling)',
        'examples': ['Sun Jun 1, 2025'],
        'extract': _extract_mikes_rubbish_date
    },
    'E.J. Harrison & Sons': {
        'format': 'M/DD/YY',
        'label': 'DATE (columnar)',
        'examples': ['9/08/25'],
        'extract': _extract_ej_harrison_sons_date
    },
    'City of Sherman': {
        'format': 'MM/DD/YYYY',
        'label': 'BILL DATE:',
        'examples': ['08/29/2025'],
        'extract': _extract_city_of_sherman_date
    },
    'Waste Zero': {
        'format': 'MM/DD/YYYY',
        'label': 'DATE (columnar)',
        'examples': ['02/28/2025'],
        'extract': _extract_waste_zero_date
    },
    'Hugill Sanitation': {
        'format': 'Weekday Month DD, YYYY',
        'label': 'TrashBilling format',
        'examples': ['Tue Dec 2, 2025'],
        'extract': _extract_hugill_sanitation_date
    },
    '3R Technology': {
        'format': 'MM/DD/YYYY',
        'label': 'INVOICE (standalone date)',
        'examples': ['04/30/2025'],
        'extract': _extract_3r_technology_date
    },
    'Tri-County Industries': {
        'format': 'MM/DD/YYYY',
        'label': 'Invoice Date:',
        'examples': ['09/01/2025'],
        'extract': _extract_tri_county_industries_date
    },
    'City of Tulsa': {
        'format': 'MM/DD/YYYY',
        'label': 'Account Summary',
        'examples': ['03/26/2025'],
        'extract': _extract_city_of_tulsa_date
    },
    'Apex Recycling & Disposal': {
        'format': 'M/DD/YYYY',
        'label': 'DATE (transaction)',
        'examples': ['11/10/2025'],
        'extract': _extract_apex_recycling_disposal_date
    },
    'HMP Inc': {
        'format': 'MM/DD/YYYY',
        'label': 'DATE (columnar)',
        'examples': ['01/01/2026'],
        'extract': _extract_hmp_inc_date
    },
    'SSW-Box Services': {
        'format': 'Weekday Month DD, YYYY',
        'label': 'TrashBilling format',
        'examples': ['Tue Dec 9, 2025'],
        'extract': _extract_ssw_box_services_date
    },
    'Hillside Solutions': {
        'format': 'MM/DD/YYYY',
        'label': 'DATE (inline)',
        'examples': ['01/15/2025'],
        'extract': _extract_hillside_solutions_date
    },
    # --- Tranche 32 ---
    'Whitecap Waste': {
        'format': 'Month DD, YYYY',
        'label': 'DATE (NavuSoft)',
        'examples': ['Dec 31, 2024'],
        'extract': _extract_whitecap_waste_date
    },
    "Jim's Sanitation": {
        'format': 'M/D/YYYY',
        'label': 'Date (columnar)',
        'examples': ['2/10/2025'],
        'extract': _extract_jims_sanitation_date
    },
    'R-Local Sanitation': {
        'format': 'Weekday Month DD, YYYY',
        'label': 'TrashBilling format',
        'examples': ['Mon Mar 10, 2025'],
        'extract': _extract_r_local_sanitation_date
    },
    'Prestige Disposal': {
        'format': 'Weekday Month DD, YYYY',
        'label': 'TrashBilling format',
        'examples': ['Thu Oct 9, 2025'],
        'extract': _extract_prestige_disposal_date
    },
    'Apple Valley Waste': {
        'format': 'MM/DD/YYYY',
        'label': 'Invoice Date',
        'examples': ['12/31/2025'],
        'extract': _extract_apple_valley_waste_date
    },
    'City of Sulphur Springs': {
        'format': 'M/DD/YYYY',
        'label': 'Date (columnar)',
        'examples': ['6/28/2025'],
        'extract': _extract_city_of_sulphur_springs_date
    },
    'Pro Disposal': {
        'format': 'Weekday Month DD, YYYY',
        'label': 'TrashBilling format',
        'examples': ['Sun Jun 1, 2025'],
        'extract': _extract_pro_disposal_date
    },
    'Royal Oak Recycling': {
        'format': 'MM/DD/YYYY',
        'label': 'After invoice No.',
        'examples': ['07/14/2025'],
        'extract': _extract_royal_oak_recycling_date
    },
    'The Trash Guys': {
        'format': 'Weekday Month DD, YYYY',
        'label': 'TrashBilling format',
        'examples': ['Tue May 20, 2025'],
        'extract': _extract_the_trash_guys_date
    },
    'Ameriwaste': {
        'format': 'Weekday Month DD, YYYY',
        'label': 'Date: (TrashBilling)',
        'examples': ['Sun Jun 1, 2025'],
        'extract': _extract_ameriwaste_date
    },
    'Black Earth Compost': {
        'format': 'MM/DD/YYYY',
        'label': 'DATE (columnar)',
        'examples': ['01/15/2025'],
        'extract': _extract_black_earth_compost_date
    },
    "Hogland's Transfer": {
        'format': 'MM/DD/YY',
        'label': 'Freight bill date',
        'examples': ['03/20/25'],
        'extract': _extract_hoglands_transfer_date
    },
    'BNB Disposal': {
        'format': 'Weekday Month DD, YYYY',
        'label': 'TrashBilling format',
        'examples': ['Sat Nov 1, 2025'],
        'extract': _extract_bnb_disposal_date
    },
    'Willey Disposal': {
        'format': 'MM/DD/YYYY',
        'label': 'DATE (columnar)',
        'examples': ['11/27/2024'],
        'extract': _extract_willey_disposal_date
    },
    'Junk King': {
        'format': 'Month DD, YYYY',
        'label': 'Invoice Date',
        'examples': ['Sep 02, 2025'],
        'extract': _extract_junk_king_date
    },
    # --- Tranche 33 ---
    'City of Hickory': {
        'format': 'MM/DD/YY',
        'label': 'BILL DATE/CYCLE',
        'examples': ['10/21/25'],
        'extract': _extract_city_of_hickory_date
    },
    'Eco Sanitation': {
        'format': 'Weekday Month DD, YYYY',
        'label': 'TrashBilling format',
        'examples': ['Tue Apr 1, 2025'],
        'extract': _extract_eco_sanitation_date
    },
    'Chambersburg Waste Paper': {
        'format': 'MM/DD/YYYY',
        'label': 'Date (columnar)',
        'examples': ['11/01/2025'],
        'extract': _extract_chambersburg_waste_paper_date
    },
    'Miamitown Auto Parts': {
        'format': 'M/D/YYYY',
        'label': 'Statement Date:',
        'examples': ['7/1/2025'],
        'extract': _extract_miamitown_auto_parts_date
    },
    'Countryside Disposal': {
        'format': 'Weekday Month DD, YYYY',
        'label': 'TrashBilling format',
        'examples': ['Tue Apr 1, 2025'],
        'extract': _extract_countryside_disposal_date
    },
    'Iron City Express': {
        'format': 'M/D/YY',
        'label': 'Invoice Date',
        'examples': ['7/1/25'],
        'extract': _extract_iron_city_express_date
    },
    'City of Great Falls': {
        'format': 'M/D/YYYY',
        'label': 'Due Date (proxy)',
        'examples': ['6/5/2025'],
        'extract': _extract_city_of_great_falls_date
    },
    "Jay Mecham's": {
        'format': 'M/D/YYYY',
        'label': 'Date (columnar)',
        'examples': ['10/6/2025'],
        'extract': _extract_jay_mechams_date
    },
    'MCUD Manatee': {
        'format': 'MM/DD',
        'label': 'Service Period',
        'examples': ['08/12'],
        'extract': _extract_mcud_manatee_date
    },
    'Hughes Trash Removal': {
        'format': 'MM/DD/YY',
        'label': 'INVOICE DATE',
        'examples': ['01/01/26'],
        'extract': _extract_hughes_trash_removal_date
    },
    'Roadrunner Sanitation': {
        'format': 'Weekday Month DD, YYYY',
        'label': 'TrashBilling format',
        'examples': ['Mon Sep 1, 2025'],
        'extract': _extract_roadrunner_sanitation_date
    },
    'Total Disposal Inc': {
        'format': 'M/DD/YYYY',
        'label': 'INVOICE DATE',
        'examples': ['4/26/2025'],
        'extract': _extract_total_disposal_inc_date
    },
    'KC Disposal': {
        'format': 'M/D/YYYY',
        'label': 'Date (columnar)',
        'examples': ['7/1/2025'],
        'extract': _extract_kc_disposal_date
    },
    'Greenway Waste': {
        'format': 'MM/DD/YYYY',
        'label': 'Service Date:',
        'examples': ['09/30/2025'],
        'extract': _extract_greenway_waste_date
    },
    'Filco': {
        'format': 'MM/DD/YYYY',
        'label': 'Invoice Date:',
        'examples': ['10/31/2025'],
        'extract': _extract_filco_date
    },
    # --- Tranche 34 ---
    'Garden State Waste Management': {
        'format': 'Weekday Month DD, YYYY',
        'label': 'TrashBilling format',
        'examples': ['Fri Mar 21, 2025'],
        'extract': _extract_garden_state_waste_management_date
    },
    'Bi-County Disposal': {
        'format': 'MM/DD/YYYY',
        'label': 'Invoice Date',
        'examples': ['07/01/2025'],
        'extract': _extract_bi_county_disposal_date
    },
    'Golden Environmental': {
        'format': 'Weekday Month DD, YYYY',
        'label': 'TrashBilling format',
        'examples': ['Mon Apr 1, 2025'],
        'extract': _extract_golden_environmental_date
    },
    'Nauset Disposal': {
        'format': 'M/D/YYYY',
        'label': 'STATEMENT DATE',
        'examples': ['10/1/2025'],
        'extract': _extract_nauset_disposal_date
    },
    'Brask Enterprises': {
        'format': 'M/D/YYYY',
        'label': 'DATE (columnar)',
        'examples': ['11/1/2025'],
        'extract': _extract_brask_enterprises_date
    },
    'Wyoming Waste Services': {
        'format': 'MM/DD/YY',
        'label': 'STATEMENT DATE',
        'examples': ['10/01/25'],
        'extract': _extract_wyoming_waste_services_date
    },
    'City of St Anthony': {
        'format': 'MM/DD/YYYY',
        'label': 'DATE (columnar)',
        'examples': ['10/01/2025'],
        'extract': _extract_city_of_st_anthony_date
    },
    'Star Waste': {
        'format': 'Weekday Month DD YYYY',
        'label': 'No comma format',
        'examples': ['Thu Oct 23 2025'],
        'extract': _extract_star_waste_date
    },
    'Reworld': {
        'format': 'MM-DD-YYYY',
        'label': 'Manifest date',
        'examples': ['10-23-2025'],
        'extract': _extract_reworld_date
    },
    'City of Conyers': {
        'format': 'MM/DD/YYYY',
        'label': 'INVOICE DATE',
        'examples': ['02/01/2025'],
        'extract': _extract_city_of_conyers_date
    },
    'Treasure Coast Recycling': {
        'format': 'MM/DD/YYYY',
        'label': 'Date (columnar)',
        'examples': ['10/15/2025'],
        'extract': _extract_treasure_coast_recycling_date
    },
    'North Georgia Waste': {
        'format': 'Weekday Month DD, YYYY',
        'label': 'TrashBilling format',
        'examples': ['Tue Mar 4, 2025'],
        'extract': _extract_north_georgia_waste_date
    },
    'Myers Container Service': {
        'format': 'Weekday Month DD, YYYY',
        'label': 'TrashBilling format',
        'examples': ['Tue Mar 4, 2025'],
        'extract': _extract_myers_container_service_date
    },
    'Keys Sanitary': {
        'format': 'MM/DD/YY',
        'label': 'INV DATE',
        'examples': ['12/01/25'],
        'extract': _extract_keys_sanitary_date
    },
    'Larry D Marshall Disposal': {
        'format': 'Weekday Month DD, YYYY',
        'label': 'TrashBilling format',
        'examples': ['Mon Sep 1, 2025'],
        'extract': _extract_larry_d_marshall_disposal_date
    },
    # --- Tranche 35 ---
    'NEI Pennsylvania': {
        'format': 'MM/DD/YYYY',
        'label': 'DATE (columnar)',
        'examples': ['11/12/2025'],
        'extract': _extract_nei_pennsylvania_date
    },
    'Container Rental Co': {
        'format': 'MM/DD/YY',
        'label': 'INV DATE (columnar)',
        'examples': ['05/31/25'],
        'extract': _extract_container_rental_co_date
    },
    'Butler Disposal Systems': {
        'format': 'Weekday Month DD, YYYY',
        'label': 'TrashBilling format',
        'examples': ['Fri May 30, 2025'],
        'extract': _extract_butler_disposal_systems_date
    },
    'Golden Triangle Waste': {
        'format': 'MM/DD/YYYY',
        'label': 'DATE (columnar)',
        'examples': ['12/25/2025'],
        'extract': _extract_golden_triangle_waste_date
    },
    'Forever Clean': {
        'format': 'Mon D, YYYY',
        'label': 'Invoice Date (columnar)',
        'examples': ['Jul 8, 2025'],
        'extract': _extract_forever_clean_date
    },
    'Glendale Arizona Utilities': {
        'format': 'MM/DD/YYYY',
        'label': 'BILL DATE (columnar)',
        'examples': ['11/05/2025'],
        'extract': _extract_glendale_arizona_utilities_date
    },
    'Omni': {
        'format': 'MM/DD/YY',
        'label': 'DATE: inline',
        'examples': ['05/22/25'],
        'extract': _extract_omni_date
    },
    'Bridge City Sanitation': {
        'format': 'M/DD/YYYY',
        'label': 'DATE (columnar)',
        'examples': ['6/30/2025'],
        'extract': _extract_bridge_city_sanitation_date
    },
    'City of Mesquite': {
        'format': 'M/DD/YY',
        'label': 'Invoice Date (reverse columnar)',
        'examples': ['4/28/25'],
        'extract': _extract_city_of_mesquite_date
    },
    'City of Oakland Park': {
        'format': 'MM/DD/YYYY',
        'label': 'Bill Date (columnar)',
        'examples': ['07/02/2025'],
        'extract': _extract_city_of_oakland_park_date
    },
    'Talon Sanitation': {
        'format': 'MM/DD/YYYY',
        'label': 'Invoice date: (columnar)',
        'examples': ['10/01/2025'],
        'extract': _extract_talon_sanitation_date
    },
    'Marpan Supply': {
        'format': 'MM/DD/YY',
        'label': 'DATE (columnar)',
        'examples': ['08/20/23'],
        'extract': _extract_marpan_supply_date
    },
    # --- Tranche 36 ---
    'Cedar Grove': {
        'format': 'MM/DD/YYYY',
        'label': 'Invoice Date (columnar)',
        'examples': ['12/31/2025'],
        'extract': _extract_cedar_grove_date
    },
    'Hotchkiss Disposal': {
        'format': 'Weekday Month DD, YYYY',
        'label': 'TrashBilling format',
        'examples': ['Mon Dec 29, 2025'],
        'extract': _extract_hotchkiss_disposal_date
    },
    'Sunshine Disposal & Recycling': {
        'format': 'M/DD/YY',
        'label': 'BILLING DATE (columnar)',
        'examples': ['6/30/25'],
        'extract': _extract_sunshine_disposal_recycling_date
    },
    'Dugger Trash Service': {
        'format': 'MM/DD/YYYY',
        'label': 'Invoice date: (columnar)',
        'examples': ['03/01/2025'],
        'extract': _extract_dugger_trash_service_date
    },
    'Waste Resources Gardena': {
        'format': 'M/DD/YYYY',
        'label': 'INVOICE DATE (columnar)',
        'examples': ['9/30/2025'],
        'extract': _extract_waste_resources_gardena_date
    },
    'Walters Sanitary Service': {
        'format': 'MM/DD/YY',
        'label': 'INV DATE (columnar)',
        'examples': ['12/31/24'],
        'extract': _extract_walters_sanitary_service_date
    },
    "Woodward's Disposal": {
        'format': 'MM/DD/YYYY',
        'label': 'Invoice Date: (columnar)',
        'examples': ['02/24/2025'],
        'extract': _extract_woodwards_disposal_date
    },
    'Al Clawson Disposal': {
        'format': 'M/DD/YY',
        'label': 'Invoice Date (columnar)',
        'examples': ['6/13/25'],
        'extract': _extract_al_clawson_disposal_date
    },
    'Mt Diablo Resource Recovery': {
        'format': 'MM/DD/YYYY',
        'label': 'Invoice Date: (inline)',
        'examples': ['05/31/2025'],
        'extract': _extract_mt_diablo_resource_recovery_date
    },
    'Blue Ridge Waste': {
        'format': 'DD Mon, YYYY',
        'label': 'Invoice Date (columnar)',
        'examples': ['30 Jun, 2025'],
        'extract': _extract_blue_ridge_waste_date
    },
    'Alpha Waste Disposal': {
        'format': 'Mon DD, YYYY',
        'label': 'Invoice Date: (inline)',
        'examples': ['Sep 30, 2025'],
        'extract': _extract_alpha_waste_disposal_date
    },
    'Texas Commercial Waste': {
        'format': 'MM/DD/YYYY',
        'label': 'Invoice Date: (inline)',
        'examples': ['06/27/2025'],
        'extract': _extract_texas_commercial_waste_date
    },
    # --- Tranche 37 ---
    "Good's Disposal": {
        'format': 'MM/DD/YYYY',
        'label': 'DATE (columnar)',
        'examples': ['08/01/2025'],
        'extract': _extract_goods_disposal_date
    },
    "Charlie's Waste": {
        'format': 'Mon-DD-YY',
        'label': 'Aug-01-25 style',
        'examples': ['Aug-01-25'],
        'extract': _extract_charlies_waste_date
    },
    'Madison Materials': {
        'format': 'MM/DD/YY',
        'label': 'INV DATE (columnar)',
        'examples': ['07/13/25'],
        'extract': _extract_madison_materials_date
    },
    'LaVeine Sanitation': {
        'format': 'MM/DD/YYYY',
        'label': 'Invoice Date (columnar)',
        'examples': ['04/30/2025'],
        'extract': _extract_laveine_sanitation_date
    },
    'T & G Sanitation': {
        'format': 'Weekday Month DD, YYYY',
        'label': 'TrashBilling format',
        'examples': ['Mon Jun 2, 2025'],
        'extract': _extract_t_g_sanitation_date
    },
    'Roadrunner Rubbish': {
        'format': 'MM/DD/YY',
        'label': 'INV DATE (columnar)',
        'examples': ['10/15/25'],
        'extract': _extract_roadrunner_rubbish_date
    },
    'Marck Recycling and Waste': {
        'format': 'Mon-DD-YY',
        'label': 'Date (columnar)',
        'examples': ['Jul-01-25'],
        'extract': _extract_marck_recycling_and_waste_date
    },
    'Elite Recycling': {
        'format': 'Mon D, YYYY',
        'label': 'Top of invoice',
        'examples': ['Jan 1, 2026'],
        'extract': _extract_elite_recycling_date
    },
    'Denali Disposal': {
        'format': 'MM/DD/YYYY',
        'label': 'Invoice Date: (inline)',
        'examples': ['10/03/2025'],
        'extract': _extract_denali_disposal_date
    },
    'Bloom Waste': {
        'format': 'MM/DD/YY',
        'label': 'INV DATE (columnar)',
        'examples': ['10/01/25'],
        'extract': _extract_bloom_waste_date
    },
    'Patterson Sanitation': {
        'format': 'MM/DD/YY',
        'label': 'BILLING DATE (columnar)',
        'examples': ['02/20/25'],
        'extract': _extract_patterson_sanitation_date
    },
    '4G Futures': {
        'format': 'M/DD/YYYY',
        'label': 'Date (columnar)',
        'examples': ['2/15/2025'],
        'extract': _extract_4g_futures_date
    },
    # --- Tranche 38 ---
    'IV Waste': {
        'format': 'MM/DD/YYYY',
        'label': 'INVOICE DATE (columnar)',
        'examples': ['12/1/2025'],
        'extract': _extract_iv_waste_date
    },
    'K & K Sanitation': {
        'format': 'MM/DD/YYYY',
        'label': 'Invoice date: (columnar)',
        'examples': ['11/01/2025'],
        'extract': _extract_k_k_sanitation_date
    },
    'Waste Harmonics': {
        'format': 'MM/DD/YYYY',
        'label': 'DATE (columnar)',
        'examples': ['10/10/2025'],
        'extract': _extract_waste_harmonics_date
    },
    'Bozeman MT Utilities': {
        'format': 'MM/DD/YYYY',
        'label': 'BILLING DATE: (inline)',
        'examples': ['09/24/2025'],
        'extract': _extract_bozeman_mt_utilities_date
    },
    'Taylor & Sons': {
        'format': 'MM/DD/YYYY',
        'label': 'DATE (columnar)',
        'examples': ['10/01/2025'],
        'extract': _extract_taylor_sons_date
    },
    'United Rentals': {
        'format': 'MM/DD/YY',
        'label': 'STATEMENT DATE (columnar)',
        'examples': ['09/30/25'],
        'extract': _extract_united_rentals_date
    },
    'Nevada Recycling': {
        'format': 'MM/DD/YYYY',
        'label': 'Payment date (columnar)',
        'examples': ['05/12/2025'],
        'extract': _extract_nevada_recycling_date
    },
    'Tygarts Valley Sanitation': {
        'format': 'MM/DD/YYYY',
        'label': 'received on (inline)',
        'examples': ['12/15/2025'],
        'extract': _extract_tygarts_valley_sanitation_date
    },
    'Miedema Sanitation': {
        'format': 'M/D/YYYY',
        'label': 'Date (columnar)',
        'examples': ['9/9/2025'],
        'extract': _extract_miedema_sanitation_date
    },
    'Quincy Recycling': {
        'format': 'MM/DD/YYYY',
        'label': 'Recv Date: (inline)',
        'examples': ['09/09/2025'],
        'extract': _extract_quincy_recycling_date
    },
    'Smurfit': {
        'format': 'M/DD/YYYY',
        'label': 'Date: (columnar)',
        'examples': ['8/31/2025'],
        'extract': _extract_smurfit_date
    },
    'Escondido Disposal': {
        'format': 'MM/DD/YY',
        'label': 'Billing Date (columnar)',
        'examples': ['08/01/25'],
        'extract': _extract_escondido_disposal_date
    },
    # --- Tranche 39 ---
    'Express Disposal': {
        'format': 'MM/DD/YYYY',
        'label': 'STATEMENT (columnar)',
        'examples': ['5/31/2025'],
        'extract': _extract_express_disposal_date
    },
    'Waste Services Manchester': {
        'format': 'MM/DD/YY',
        'label': 'INV DATE (columnar)',
        'examples': ['06/30/25'],
        'extract': _extract_waste_services_manchester_date
    },
    "Ava's Waste Removal": {
        'format': 'M/D/YYYY',
        'label': 'received on (TrashBilling)',
        'examples': ['2/7/2025'],
        'extract': _extract_avas_waste_removal_date
    },
    'BKI Recycling': {
        'format': 'DD Mon YYYY',
        'label': 'Inline after invoice number',
        'examples': ['18 Nov 2025'],
        'extract': _extract_bki_recycling_date
    },
    'Valley Sanitation LLC': {
        'format': 'M/D/YYYY',
        'label': 'received on (TrashBilling)',
        'examples': ['12/29/2025'],
        'extract': _extract_valley_sanitation_llc_date
    },
    'Ridgerunner Container': {
        'format': 'MM/DD/YY',
        'label': 'DATE (columnar)',
        'examples': ['06/30/25'],
        'extract': _extract_ridgerunner_container_date
    },
    'Recycling Services of Florida': {
        'format': 'Mon-DD-YY',
        'label': 'DATE (columnar)',
        'examples': ['Dec-31-25'],
        'extract': _extract_recycling_services_of_florida_date
    },
    'Rick Taylor': {
        'format': 'Month DD, YYYY',
        'label': 'DATE:',
        'examples': ['December 31, 2025'],
        'extract': _extract_rick_taylor_date
    },
    'Klumm Brothers': {
        'format': 'Weekday Mon DD, YYYY',
        'label': 'TrashBilling format',
        'examples': ['Tue Apr 29, 2025'],
        'extract': _extract_klumm_brothers_date
    },
    'Green Guy Recycling': {
        'format': 'MM/DD/YYYY',
        'label': 'Invoice date:',
        'examples': ['08/27/2025'],
        'extract': _extract_green_guy_recycling_date
    },
    'MARS City of Beatrice': {
        'format': 'MM/DD/YYYY',
        'label': 'STATEMENT Date (columnar)',
        'examples': ['05/01/2025'],
        'extract': _extract_mars_city_of_beatrice_date
    },
    'Midwest Disposal IL': {
        'format': 'MM/DD/YYYY',
        'label': 'Invoice date: (columnar)',
        'examples': ['05/20/2025'],
        'extract': _extract_midwest_disposal_il_date
    },
    # --- Tranche 40 ---
    'Lake Disposal Service': {
        'format': 'M/D/YYYY',
        'label': 'DATE (columnar)',
        'examples': ['6/25/2025'],
        'extract': _extract_lake_disposal_service_date
    },
    'Tropical Trash': {
        'format': 'Mon D, YYYY',
        'label': 'DATE (NavuSoft columnar)',
        'examples': ['Jun 4, 2025'],
        'extract': _extract_tropical_trash_date
    },
    'Troupe Waste': {
        'format': 'Mon-DD-YY',
        'label': 'Date (columnar)',
        'examples': ['Jun-30-25'],
        'extract': _extract_troupe_waste_date
    },
    'A&W Iron Metal': {
        'format': 'MM/DD/YYYY',
        'label': 'Invoice Date:',
        'examples': ['06/30/2025'],
        'extract': _extract_aw_iron_metal_date
    },
    'Chesapeake Waste': {
        'format': 'MM/DD/YYYY',
        'label': 'Statement Date (reverse columnar)',
        'examples': ['10/01/2025'],
        'extract': _extract_chesapeake_waste_date
    },
    'Expert Transportation': {
        'format': 'M/D/YYYY',
        'label': 'Date (columnar)',
        'examples': ['4/1/2025'],
        'extract': _extract_expert_transportation_date
    },
    'Seadrunar Recycling': {
        'format': 'MM/DD/YYYY',
        'label': 'Invoice area date',
        'examples': ['06/30/2025'],
        'extract': _extract_seadrunar_recycling_date
    },
    'Greenbrier Valley Solid Waste': {
        'format': 'Weekday Mon DD, YYYY',
        'label': 'TrashBilling format',
        'examples': ['Wed Jun 25, 2025'],
        'extract': _extract_greenbrier_valley_solid_waste_date
    },
    'BTS Inc': {
        'format': 'M/D/YYYY',
        'label': 'Date (columnar)',
        'examples': ['7/10/2025'],
        'extract': _extract_bts_inc_date
    },
    'Town & Country Disposal': {
        'format': 'MM/DD/YY',
        'label': 'STATEMENT DATE (columnar)',
        'examples': ['01/01/26'],
        'extract': _extract_town_country_disposal_date
    },
    'Haul Away Waste': {
        'format': 'MM/DD/YYYY',
        'label': 'INVOICE DATE (reverse columnar)',
        'examples': ['01/24/2025'],
        'extract': _extract_haul_away_waste_date
    },
    'Napa Recycling': {
        'format': 'MM/DD/YYYY',
        'label': 'STATEMENT DATE:',
        'examples': ['05/30/2025'],
        'extract': _extract_napa_recycling_date
    },
    # --- Tranche 41 ---
    'City of Lakeland FL': {
        'format': 'MM/DD/YYYY',
        'label': 'Billing Date:',
        'examples': ['02/27/2025'],
        'extract': _extract_city_of_lakeland_fl_date
    },
    'WM Compactor Solutions': {
        'format': 'M/D/YYYY',
        'label': 'Invoice Date: (columnar)',
        'examples': ['2/28/2025'],
        'extract': _extract_wm_compactor_solutions_date
    },
    'Mills Brothers': {
        'format': 'MM-DD-YY',
        'label': 'INVOICE DATE:',
        'examples': ['05-06-25'],
        'extract': _extract_mills_brothers_date
    },
    'Arrowhead Waste': {
        'format': 'MM/DD/YYYY',
        'label': 'Invoice Date:',
        'examples': ['01/01/2026'],
        'extract': _extract_arrowhead_waste_date
    },
    'Waterman Recycling': {
        'format': 'M/D/YYYY',
        'label': 'received on (TrashBilling)',
        'examples': ['3/26/2025'],
        'extract': _extract_waterman_recycling_date
    },
    'Ramona Disposal': {
        'format': 'MM/DD/YY',
        'label': 'Billing Date (columnar)',
        'examples': ['09/30/25'],
        'extract': _extract_ramona_disposal_date
    },
    'Redwood Waste': {
        'format': 'MM/DD/YY',
        'label': 'STATEMENT DATE (columnar)',
        'examples': ['03/01/25'],
        'extract': _extract_redwood_waste_date
    },
    'Tri-State Disposal': {
        'format': 'MM/DD/YYYY',
        'label': 'Invoice Date (columnar)',
        'examples': ['06/01/2025'],
        'extract': _extract_tri_state_disposal_date
    },
    'Enevo': {
        'format': 'MM/DD/YYYY',
        'label': 'DATE (columnar)',
        'examples': ['06/01/2025'],
        'extract': _extract_enevo_date
    },
    'JD Parker': {
        'format': 'MM/DD/YYYY',
        'label': 'Invoice Date: (columnar)',
        'examples': ['09/30/2025'],
        'extract': _extract_jd_parker_date
    },
    'AJ Waste Systems': {
        'format': 'M/D/YY',
        'label': 'Invoice Date (reverse columnar)',
        'examples': ['3/1/25'],
        'extract': _extract_aj_waste_systems_date
    },
    'Darob': {
        'format': 'M/D/YYYY',
        'label': 'Date (columnar)',
        'examples': ['5/1/2025'],
        'extract': _extract_darob_date
    },
    # --- Tranche 42 ---
    "Weaver's Sanitation": {
        'format': 'M/D/YYYY',
        'label': 'INVOICE DATE (columnar)',
        'examples': ['3/31/2025'],
        'extract': _extract_weavers_sanitation_date
    },
    'Akat Scrap Metal': {
        'format': 'M/D/YYYY',
        'label': 'Date (reverse columnar)',
        'examples': ['3/3/2025'],
        'extract': _extract_akat_scrap_metal_date
    },
    'City of Bakersfield': {
        'format': 'MM/DD/YYYY',
        'label': 'Invoice Date (inline)',
        'examples': ['06/30/2025'],
        'extract': _extract_city_of_bakersfield_date
    },
    'City of Visalia': {
        'format': 'MM/DD/YYYY',
        'label': 'FROM date range',
        'examples': ['12/01/2024'],
        'extract': _extract_city_of_visalia_date
    },
    'Shank Waste': {
        'format': 'MM/DD/YYYY',
        'label': 'Invoice Date:',
        'examples': ['05/01/2025'],
        'extract': _extract_shank_waste_date
    },
    "Steve's Sanitation": {
        'format': 'M/D/YYYY',
        'label': 'received on (TrashBilling)',
        'examples': ['2/25/2025'],
        'extract': _extract_steves_sanitation_date
    },
    'Lemhi Sanitation': {
        'format': 'M/D/YYYY',
        'label': 'Date (columnar)',
        'examples': ['1/1/2025'],
        'extract': _extract_lemhi_sanitation_date
    },
    'Weidle Sanitation': {
        'format': 'MM/DD/YYYY',
        'label': 'DATE (columnar)',
        'examples': ['07/01/2025'],
        'extract': _extract_weidle_sanitation_date
    },
    'Choice Waste Services': {
        'format': 'Mon DD, YYYY',
        'label': 'DATE (NavuSoft columnar)',
        'examples': ['Dec 31, 2025'],
        'extract': _extract_choice_waste_services_date
    },
    'Hale County Public Works': {
        'format': 'MM/DD/YYYY',
        'label': 'SERVICE DATE',
        'examples': ['12/01/2025'],
        'extract': _extract_hale_county_public_works_date
    },
    'Pike County Solid Waste': {
        'format': 'M/D/YYYY',
        'label': 'received on (TrashBilling)',
        'examples': ['11/28/2025'],
        'extract': _extract_pike_county_solid_waste_date
    },
    'P&M Reis Trucking': {
        'format': 'MM/DD/YYYY',
        'label': 'Invoice Date (inline)',
        'examples': ['08/02/2025'],
        'extract': _extract_pm_reis_trucking_date
    },
    # --- Tranche 43 ---
    'Full Circle Recycling': {
        'format': 'MM/DD/YY',
        'label': 'Invoice Date (columnar)',
        'examples': ['10/11/25'],
        'extract': _extract_full_circle_recycling_date
    },
    'Kohlmorgan Hauling': {
        'format': 'MM/DD/YYYY',
        'label': 'DATE (inline)',
        'examples': ['10/15/2025'],
        'extract': _extract_kohlmorgan_hauling_date
    },
    'Econo Waste': {
        'format': 'MM/DD/YYYY',
        'label': 'Statement Date (columnar)',
        'examples': ['10/30/2025'],
        'extract': _extract_econo_waste_date
    },
    'RaeKar': {
        'format': 'M/D/YYYY',
        'label': 'received on (TrashBilling)',
        'examples': ['7/7/2025'],
        'extract': _extract_raekar_date
    },
    'Action Trucking': {
        'format': 'DD Mon, YYYY',
        'label': 'Invoice Date',
        'examples': ['02 Mar, 2025'],
        'extract': _extract_action_trucking_date
    },
    'Whites Sanitation': {
        'format': 'MM/DD/YY',
        'label': 'INV DATE (columnar)',
        'examples': ['11/01/25'],
        'extract': _extract_whites_sanitation_date
    },
    'Lance Refuse': {
        'format': 'MM/DD/YYYY',
        'label': 'DATE (inline)',
        'examples': ['06/01/2025'],
        'extract': _extract_lance_refuse_date
    },
    'Lift Waste': {
        'format': 'MM/DD/YYYY',
        'label': 'DATE (columnar)',
        'examples': ['11/01/2025'],
        'extract': _extract_lift_waste_date
    },
    'Long Beach Container': {
        'format': 'M/D/YYYY',
        'label': 'Date (columnar)',
        'examples': ['7/1/2025'],
        'extract': _extract_long_beach_container_date
    },
    'Pullman Disposal': {
        'format': 'MM/DD/YYYY',
        'label': 'INVOICE DATE (columnar)',
        'examples': ['01/01/2025'],
        'extract': _extract_pullman_disposal_date
    },
    'EZ Disposal': {
        'format': 'Mon DD, YYYY',
        'label': 'DATE (NavuSoft columnar)',
        'examples': ['Nov 30, 2025'],
        'extract': _extract_ez_disposal_date
    },
    'Control Waste': {
        'format': 'MM/DD/YY',
        'label': 'Date: (columnar)',
        'examples': ['11/20/25'],
        'extract': _extract_control_waste_date
    },
    # --- Tranche 44 ---
    'NVA Services': {
        'format': 'MM/DD/YYYY',
        'label': 'Invoice Date (inline)',
        'examples': ['05/01/2025'],
        'extract': _extract_nva_services_date
    },
    'Tahoe Basin Container': {
        'format': 'MM/DD/YYYY',
        'label': 'Statement Date (columnar)',
        'examples': ['12/01/2025'],
        'extract': _extract_tahoe_basin_container_date
    },
    'AWS': {
        'format': 'Mon DD, YYYY',
        'label': 'DATE (NavuSoft columnar)',
        'examples': ['Dec 31, 2025'],
        'extract': _extract_aws_date
    },
    'Boston Baler': {
        'format': 'MM/DD/YYYY',
        'label': 'Invoice Date (inline)',
        'examples': ['08/01/2025'],
        'extract': _extract_boston_baler_date
    },
    'City of Foley': {
        'format': 'M/D/YYYY',
        'label': 'DATE (columnar)',
        'examples': ['12/1/2025'],
        'extract': _extract_city_of_foley_date
    },
    'City of Richardson': {
        'format': 'MM/DD/YYYY',
        'label': 'DATE (columnar)',
        'examples': ['12/01/2025'],
        'extract': _extract_city_of_richardson_date
    },
    'City of Sallisaw': {
        'format': 'M/D/YYYY',
        'label': 'received on (TrashBilling)',
        'examples': ['11/7/2025'],
        'extract': _extract_city_of_sallisaw_date
    },
    'Lincoln County Solid Waste': {
        'format': 'MM/DD/YYYY',
        'label': 'DATE (columnar)',
        'examples': ['07/01/2025'],
        'extract': _extract_lincoln_county_solid_waste_date
    },
    'Norris Sanitation': {
        'format': 'MM/DD/YYYY',
        'label': 'Date: (inline)',
        'examples': ['12/31/2025'],
        'extract': _extract_norris_sanitation_date
    },
    'Kamps Pallets': {
        'format': 'MM/DD/YYYY',
        'label': 'Invoice Date (inline)',
        'examples': ['10/31/2025'],
        'extract': _extract_kamps_pallets_date
    },
    'Crane Roll-Off': {
        'format': 'M/D/YYYY',
        'label': 'DATE (columnar)',
        'examples': ['7/1/2025'],
        'extract': _extract_crane_roll_off_date
    },
    'Heartland Waste Management': {
        'format': 'MM/DD/YYYY',
        'label': 'Invoice Date: (inline)',
        'examples': ['11/01/2025'],
        'extract': _extract_heartland_waste_management_date
    },
    # --- Tranche 45 ---
    'City of Tulare': {
        'format': 'MM/DD/YYYY',
        'label': 'Billing Date: (columnar)',
        'examples': ['02/28/2025'],
        'extract': _extract_city_of_tulare_date
    },
    'Rhino Waste': {
        'format': 'Mon DD, YYYY',
        'label': 'Date: (inline)',
        'examples': ['Mar 31, 2025'],
        'extract': _extract_rhino_waste_date
    },
    'Miller Enterprises': {
        'format': 'Weekday Mon DD, YYYY',
        'label': 'TrashBilling date',
        'examples': ['Tue Jan 6, 2026'],
        'extract': _extract_miller_enterprises_date
    },
    'City of Mesa': {
        'format': 'MM/DD/YY',
        'label': 'Bill Date: (inline)',
        'examples': ['03/19/25'],
        'extract': _extract_city_of_mesa_date
    },
    'Cowboy Sanitation': {
        'format': 'MM/DD/YYYY',
        'label': 'received on (TrashBilling)',
        'examples': ['10/30/2025'],
        'extract': _extract_cowboy_sanitation_date
    },
    'CWRR': {
        'format': 'M/D/YY',
        'label': 'SERVICE PERIOD (start date)',
        'examples': ['5/1/25'],
        'extract': _extract_cwrr_date
    },
    'City of Fayette': {
        'format': 'MM/DD/YY',
        'label': 'SERVICE TO (columnar)',
        'examples': ['07/15/25'],
        'extract': _extract_city_of_fayette_date
    },
    'Premier Disposal': {
        'format': 'MM/DD/YYYY',
        'label': 'Invoice Date (wide columnar)',
        'examples': ['03/03/2025'],
        'extract': _extract_premier_disposal_date
    },
    'Nowrush Recycling': {
        'format': 'MM/DD/YYYY',
        'label': 'DATE (wide columnar)',
        'examples': ['02/19/2025'],
        'extract': _extract_nowrush_recycling_date
    },
    'Seaside Waste': {
        'format': 'MM/DD/YYYY',
        'label': 'Invoice Date: (inline)',
        'examples': ['02/01/2025'],
        'extract': _extract_seaside_waste_date
    },
    'City of Temple TX': {
        'format': 'MM/DD/YYYY',
        'label': 'Bill Date (columnar)',
        'examples': ['05/12/2025'],
        'extract': _extract_city_of_temple_tx_date
    },
    'Marin Sanitary': {
        'format': 'MM/DD/YYYY',
        'label': 'Billing Period (columnar)',
        'examples': ['06/02/2025'],
        'extract': _extract_marin_sanitary_date
    },
    # --- Tranche 46 ---
    'City Sanitary Service': {
        'format': 'Month DD, YYYY',
        'label': 'Bill Date (wide columnar)',
        'examples': ['October 31, 2025'],
        'extract': _extract_city_sanitary_service_date
    },
    'Byre Brothers': {
        'format': 'M/D/YYYY',
        'label': 'received on (TrashBilling)',
        'examples': ['7/31/2025'],
        'extract': _extract_byre_brothers_date
    },
    'Sanitation Services': {
        'format': 'MM/DD/YYYY',
        'label': 'INVOICE DATE: (wide columnar)',
        'examples': ['04/30/2025'],
        'extract': _extract_sanitation_services_date
    },
    'Cook Maintenance': {
        'format': 'M/D/YYYY',
        'label': 'Date (wide columnar)',
        'examples': ['12/3/2025'],
        'extract': _extract_cook_maintenance_date
    },
    'Florida Waste Solutions': {
        'format': 'M/D/YY',
        'label': 'Invoice Date (columnar)',
        'examples': ['2/28/25'],
        'extract': _extract_florida_waste_solutions_date
    },
    'Empire Recycling Corporation': {
        'format': 'MM/DD/YYYY',
        'label': 'Recv Date: (inline)',
        'examples': ['11/17/2025'],
        'extract': _extract_empire_recycling_corporation_date
    },
    'B&L Disposal': {
        'format': 'MM/DD/YYYY',
        'label': 'Invoice Date (columnar)',
        'examples': ['11/01/2025'],
        'extract': _extract_bl_disposal_date
    },
    'HEM Service Company': {
        'format': 'M/D/YYYY',
        'label': 'Date (wide columnar)',
        'examples': ['3/18/2025'],
        'extract': _extract_hem_service_company_date
    },
    'Shred360': {
        'format': 'MM/DD/YYYY',
        'label': 'DATE (inline)',
        'examples': ['05/01/2025'],
        'extract': _extract_shred360_date
    },
    'William Sullivan': {
        'format': 'M/D/YYYY',
        'label': 'Date (wide columnar)',
        'examples': ['10/1/2025'],
        'extract': _extract_william_sullivan_date
    },
    'MR & E': {
        'format': 'M/D/YY',
        'label': 'Bill Date: (inline)',
        'examples': ['10/1/25'],
        'extract': _extract_mr_e_date
    },
    'Local Waste Solution': {
        'format': 'MM/DD/YYYY',
        'label': 'Invoice date: (inline)',
        'examples': ['04/01/2025'],
        'extract': _extract_local_waste_solution_date
    },
    # --- Tranche 47 ---
    'Paso Robles Waste': {
        'format': 'M/D/YY',
        'label': 'Invoice Date (wide columnar)',
        'examples': ['9/30/25'],
        'extract': _extract_paso_robles_waste_date
    },
    'Coos Bay Sanitary': {
        'format': 'MM/DD/YYYY',
        'label': 'STATEMENT DATE (wide columnar)',
        'examples': ['09/02/2025'],
        'extract': _extract_coos_bay_sanitary_date
    },
    'Porter Trash': {
        'format': 'MM/DD/YYYY',
        'label': 'DATE (wide columnar)',
        'examples': ['09/01/2025'],
        'extract': _extract_porter_trash_date
    },
    'ABS Sanitation': {
        'format': 'Weekday Mon DD, YYYY',
        'label': 'TrashBilling date',
        'examples': ['Sat Oct 4, 2025'],
        'extract': _extract_abs_sanitation_date
    },
    'Tennis Sanitation': {
        'format': 'MM/DD/YYYY',
        'label': 'Billing Date (inline)',
        'examples': ['04/24/2025'],
        'extract': _extract_tennis_sanitation_date
    },
    'Rubatino Refuse': {
        'format': 'M/D/YY',
        'label': 'INVOICE NUMBER area',
        'examples': ['10/1/25'],
        'extract': _extract_rubatino_refuse_date
    },
    'Waterman Recy & Disposal': {
        'format': 'M/D/YY',
        'label': 'Bill Date: (inline)',
        'examples': ['12/1/25'],
        'extract': _extract_waterman_recy_disposal_date
    },
    'H-Town Hauling': {
        'format': 'M/D/YY',
        'label': 'Due (columnar)',
        'examples': ['1/1/26'],
        'extract': _extract_h_town_hauling_date
    },
    'Deep South Sanitation': {
        'format': 'M/D/YYYY',
        'label': 'received on (TrashBilling)',
        'examples': ['5/23/2025'],
        'extract': _extract_deep_south_sanitation_date
    },
    'Hepaco': {
        'format': 'MM/DD/YYYY',
        'label': 'Invoice/Last Service Date',
        'examples': ['01/15/2025'],
        'extract': _extract_hepaco_date
    },
    'Fayette Waste': {
        'format': 'MM/DD/YY',
        'label': 'INV DATE (columnar)',
        'examples': ['09/26/25'],
        'extract': _extract_fayette_waste_date
    },
    'Pacific Disposal': {
        'format': 'MM/DD/YY',
        'label': 'STATEMENT DATE (wide columnar)',
        'examples': ['11/01/25'],
        'extract': _extract_pacific_disposal_date
    },
    # --- Tranche 48 ---
    'Waste Control': {
        'format': 'MM/DD/YYYY',
        'label': 'INVOICE DATE: (wide columnar)',
        'examples': ['07/31/2025'],
        'extract': _extract_waste_control_date
    },
    'T-Mac Inc': {
        'format': 'M/D/YYYY',
        'label': 'received on (TrashBilling)',
        'examples': ['8/26/2025'],
        'extract': _extract_t_mac_inc_date
    },
    'Swinger Sanitation': {
        'format': 'M/D/YYYY',
        'label': 'Invoice Date: (columnar)',
        'examples': ['10/1/2025'],
        'extract': _extract_swinger_sanitation_date
    },
    'Barbarino Disposal': {
        'format': 'M/D/YYYY',
        'label': 'Bill Date: (columnar)',
        'examples': ['1/21/2025'],
        'extract': _extract_barbarino_disposal_date
    },
    'Bavarian Waste': {
        'format': 'MM/DD/YYYY',
        'label': 'INVOICE DATE: (columnar)',
        'examples': ['12/31/2024'],
        'extract': _extract_bavarian_waste_date
    },
    'City of Ketchikan': {
        'format': 'MM/DD/YYYY',
        'label': 'Date of Bill (columnar)',
        'examples': ['05/29/2025'],
        'extract': _extract_city_of_ketchikan_date
    },
    'Oregon City Garbage': {
        'format': 'MM/DD/YY',
        'label': 'INVOICE DATE (wide columnar)',
        'examples': ['11/25/25'],
        'extract': _extract_oregon_city_garbage_date
    },
    'Maverick Waste': {
        'format': 'Weekday Mon DD, YYYY',
        'label': 'TrashBilling date',
        'examples': ['Tue Jun 10, 2025'],
        'extract': _extract_maverick_waste_date
    },
    'Gardner Disposal Service': {
        'format': 'MM/DD/YYYY',
        'label': 'NOTICE DATE: (columnar)',
        'examples': ['06/01/2025'],
        'extract': _extract_gardner_disposal_service_date
    },
    'Gresham Sanitary Service': {
        'format': 'MM/DD/YYYY',
        'label': 'Bill Date (columnar)',
        'examples': ['11/03/2025'],
        'extract': _extract_gresham_sanitary_service_date
    },
    'Douglas Disposal': {
        'format': 'MM/DD/YYYY',
        'label': 'Statement Date (wide columnar)',
        'examples': ['05/01/2025'],
        'extract': _extract_douglas_disposal_date
    },
    'A1 Porta Potty': {
        'format': 'Mon DD, YYYY',
        'label': 'Date (columnar)',
        'examples': ['Mar 04, 2025'],
        'extract': _extract_a1_porta_potty_date
    },
    # --- Tranche 49 ---
    'Modern Disposal': {
        'format': 'MM/DD/YYYY',
        'label': 'Service Date: (inline)',
        'examples': ['05/19/2025'],
        'extract': _extract_modern_disposal_date
    },
    'Bower Disposal': {
        'format': 'Weekday Mon DD, YYYY',
        'label': 'Inline date',
        'examples': ['Wed Dec 31, 2025'],
        'extract': _extract_bower_disposal_date
    },
    'Arg Services': {
        'format': 'MM/DD/YYYY',
        'label': 'DATE (inline)',
        'examples': ['03/11/2025'],
        'extract': _extract_arg_services_date
    },
    'Sound Disposal Inc': {
        'format': 'MM/DD/YYYY',
        'label': 'Date: (columnar)',
        'examples': ['03/01/2025'],
        'extract': _extract_sound_disposal_inc_date
    },
    'Area Refuse': {
        'format': 'MM/DD/YYYY',
        'label': 'INVOICE DATE (columnar)',
        'examples': ['04/01/2025'],
        'extract': _extract_area_refuse_date
    },
    'Bozzuto BRS Services': {
        'format': 'M/D/YY',
        'label': 'Invoice Date (wide columnar)',
        'examples': ['4/1/25'],
        'extract': _extract_bozzuto_brs_services_date
    },
    'City of Winters': {
        'format': 'MM/DD/YYYY',
        'label': 'Invoice Date: (reverse columnar)',
        'examples': ['08/31/2025'],
        'extract': _extract_city_of_winters_date
    },
    'R&S Waste': {
        'format': 'MM/DD/YYYY',
        'label': 'Invoice Date: (inline)',
        'examples': ['11/01/2025'],
        'extract': _extract_rs_waste_date
    },
    'WB Waste Solutions': {
        'format': 'M/D/YYYY',
        'label': 'INVOICE DATE (columnar)',
        'examples': ['5/31/2025'],
        'extract': _extract_wb_waste_solutions_date
    },
    'All State Waste Inc': {
        'format': 'Mon DD, YYYY',
        'label': 'DATE (wide columnar)',
        'examples': ['Dec 31, 2025'],
        'extract': _extract_all_state_waste_inc_date
    },
    'Perdue Environmental': {
        'format': 'M/D/YY',
        'label': 'Invoice Date: (wide columnar)',
        'examples': ['4/18/25'],
        'extract': _extract_perdue_environmental_date
    },
    'Sanitation One': {
        'format': 'MM/DD/YYYY',
        'label': 'DATE (wide columnar)',
        'examples': ['10/28/2025'],
        'extract': _extract_sanitation_one_date
    },
    # --- Tranche 50 ---
    "Bud's Clean Up Service": {
        'format': 'MM/DD/YYYY',
        'label': 'Invoice date: (wide columnar)',
        'examples': ['09/27/2025'],
        'extract': _extract_buds_clean_up_service_date
    },
    'East Central Kansas': {
        'format': 'Weekday Mon DD, YYYY',
        'label': 'Date: (inline)',
        'examples': ['Tue Nov 25, 2025'],
        'extract': _extract_east_central_kansas_date
    },
    'Wisneski Westmoreland': {
        'format': 'Weekday Mon DD, YYYY',
        'label': 'TrashBilling date',
        'examples': ['Tue Dec 2, 2025'],
        'extract': _extract_wisneski_westmoreland_date
    },
    'The Shred Truck': {
        'format': 'MM/DD/YYYY',
        'label': 'Date: (columnar)',
        'examples': ['09/26/2025'],
        'extract': _extract_the_shred_truck_date
    },
    'Ideal Trash and Recycling': {
        'format': 'MM/DD/YYYY',
        'label': 'Invoice date: (wide columnar)',
        'examples': ['10/01/2025'],
        'extract': _extract_ideal_trash_and_recycling_date
    },
    'Syracuse Haulers': {
        'format': 'MM/DD/YYYY',
        'label': 'Date (wide columnar)',
        'examples': ['06/01/2025'],
        'extract': _extract_syracuse_haulers_date
    },
    'Coastal Environmental Service': {
        'format': 'MM/DD/YYYY',
        'label': 'INVOICE DATE (wide columnar)',
        'examples': ['10/01/2025'],
        'extract': _extract_coastal_environmental_service_date
    },
    'Washler Garbage': {
        'format': 'Mon DD, YYYY',
        'label': 'INVOICE DATE (NavuSoft columnar)',
        'examples': ['May 1, 2025'],
        'extract': _extract_washler_garbage_date
    },
    'City of Casper': {
        'format': 'MM/DD/YYYY',
        'label': 'Issued (inline)',
        'examples': ['12/05/2025'],
        'extract': _extract_city_of_casper_date
    },
    'City of Boynton Beach': {
        'format': 'MM/DD/YYYY',
        'label': 'Bill Date: (columnar)',
        'examples': ['02/26/2025'],
        'extract': _extract_city_of_boynton_beach_date
    },
    'Veolia': {
        'format': 'M/D/YY',
        'label': 'Invoice Date: (wide columnar)',
        'examples': ['9/1/25'],
        'extract': _extract_veolia_date
    },
    'Madras Sanitary Service': {
        'format': 'M/D/YYYY',
        'label': 'received on (TrashBilling)',
        'examples': ['2/20/2025'],
        'extract': _extract_madras_sanitary_service_date
    },
    # --- Tranche 51 ---
    'Miles City Sanitation': {
        'format': 'MM/DD/YY',
        'label': 'INV DATE (columnar)',
        'examples': ['10/01/25'],
        'extract': _extract_miles_city_sanitation_date
    },
    'Mazza Recycling': {
        'format': 'M/D/YYYY',
        'label': 'INVOICE DATE (columnar)',
        'examples': ['7/1/2025'],
        'extract': _extract_mazza_recycling_date
    },
    'Going Green Recycle': {
        'format': 'M/D/YYYY',
        'label': 'Date (columnar)',
        'examples': ['6/10/2025'],
        'extract': _extract_going_green_recycle_date
    },
    'City of McDonough': {
        'format': 'MM/DD/YYYY',
        'label': 'Due Date (columnar)',
        'examples': ['06/01/2025'],
        'extract': _extract_city_of_mcdonough_date
    },
    'GreenWaste': {
        'format': 'MM/DD/YYYY',
        'label': 'STATEMENT DATE: (columnar)',
        'examples': ['04/01/2025'],
        'extract': _extract_greenwaste_date
    },
    'Trinity Disposal': {
        'format': 'M/D/YYYY',
        'label': 'received on (TrashBilling)',
        'examples': ['2/19/2025'],
        'extract': _extract_trinity_disposal_date
    },
    'Document Destruction of Virginia': {
        'format': 'M/D/YYYY',
        'label': 'Services through (inline)',
        'examples': ['9/3/2025'],
        'extract': _extract_document_destruction_of_virginia_date
    },
    'Sutton Disposal': {
        'format': 'M/D/YYYY',
        'label': 'received on (TrashBilling)',
        'examples': ['11/3/2025'],
        'extract': _extract_sutton_disposal_date
    },
    'Waste Advantage': {
        'format': 'MM/DD/YYYY',
        'label': 'Invoice Date: (inline)',
        'examples': ['09/01/2025'],
        'extract': _extract_waste_advantage_date
    },
    'City of Snellville': {
        'format': 'M/D/YYYY',
        'label': 'Due Date (columnar)',
        'examples': ['3/17/2025'],
        'extract': _extract_city_of_snellville_date
    },
    "Thompson's Sanitary Service": {
        'format': 'M/D/YYYY',
        'label': 'Bill Date (columnar)',
        'examples': ['5/31/2025'],
        'extract': _extract_thompsons_sanitary_service_date
    },
    'City of Mont Belvieu': {
        'format': 'M/D/YYYY',
        'label': 'DATE: (inline)',
        'examples': ['7/7/2025'],
        'extract': _extract_city_of_mont_belvieu_date
    },
    # --- Tranche 52 ---
    'American Sanitation': {
        'format': 'Mon DD, YYYY',
        'label': 'Invoice Date (columnar)',
        'examples': ['Aug 11, 2025'],
        'extract': _extract_american_sanitation_date
    },
    'Solid Rock Waste': {
        'format': 'M/D/YYYY',
        'label': 'received on (TrashBilling)',
        'examples': ['1/12/2026'],
        'extract': _extract_solid_rock_waste_date
    },
    'Happy Can Disposal': {
        'format': 'Mon DD, YYYY',
        'label': 'Issued Date: (columnar)',
        'examples': ['May 31, 2025'],
        'extract': _extract_happy_can_disposal_date
    },
    'Cloquet Sanitary': {
        'format': 'MM/DD/YYYY',
        'label': 'DATE (transaction list)',
        'examples': ['02/04/2025'],
        'extract': _extract_cloquet_sanitary_date
    },
    'Miami Waste Paper': {
        'format': 'M/D/YYYY',
        'label': 'Date (columnar)',
        'examples': ['4/1/2025'],
        'extract': _extract_miami_waste_paper_date
    },
    'City of Tracy': {
        'format': 'MM/DD/YYYY',
        'label': 'Bill Date (inline)',
        'examples': ['08/28/2025'],
        'extract': _extract_city_of_tracy_date
    },
    'City of Mount Vernon WA': {
        'format': 'MM/DD/YYYY',
        'label': 'BILL DATE (wide columnar)',
        'examples': ['08/01/2025'],
        'extract': _extract_city_of_mount_vernon_wa_date
    },
    'RightAway RollOff': {
        'format': 'M/D/YYYY',
        'label': 'Date (columnar)',
        'examples': ['7/31/2025'],
        'extract': _extract_rightaway_rolloff_date
    },
    'City of Windcrest': {
        'format': 'MM/DD/YYYY',
        'label': 'Bill Date (wide columnar)',
        'examples': ['09/22/2025'],
        'extract': _extract_city_of_windcrest_date
    },
    'BGL Suburban Garbage': {
        'format': 'MM/DD/YYYY',
        'label': 'STATEMENT DATE (columnar)',
        'examples': ['07/31/2025'],
        'extract': _extract_bgl_suburban_garbage_date
    },
    'Real Waste Solutions': {
        'format': 'DD Mon YYYY',
        'label': 'date inline',
        'examples': ['01 Oct 2025'],
        'extract': _extract_real_waste_solutions_date
    },
    'Two Men and a Junk Truck': {
        'format': 'MM/DD/YYYY',
        'label': 'Service Date (columnar)',
        'examples': ['12/13/2024'],
        'extract': _extract_two_men_and_a_junk_truck_date
    },
    # --- Tranche 53 ---
    'Moler Sanitation': {
        'format': 'Weekday Mon DD, YYYY',
        'label': 'TrashBilling date',
        'examples': ['Mon Mar 31, 2025'],
        'extract': _extract_moler_sanitation_date
    },
    'Lakeland Disposal WI': {
        'format': 'Month DD YYYY',
        'label': 'Date (columnar)',
        'examples': ['October 22 2025'],
        'extract': _extract_lakeland_disposal_wi_date
    },
    'Shawnee County Solid Waste': {
        'format': 'Mon DD, YYYY',
        'label': 'DUE DATE (wide columnar)',
        'examples': ['Dec 15, 2025'],
        'extract': _extract_shawnee_county_solid_waste_date
    },
    'Brandon Industrial Parts': {
        'format': 'DD MMM YY',
        'label': 'Invoice Date (inline)',
        'examples': ['21 MAR 25'],
        'extract': _extract_brandon_industrial_parts_date
    },
    'Cumberland Services': {
        'format': 'Mon DD, YYYY',
        'label': 'DATE (columnar)',
        'examples': ['Feb 28, 2025'],
        'extract': _extract_cumberland_services_date
    },
    "Hartel's": {
        'format': 'MM/DD/YYYY',
        'label': 'Invoice Date (columnar)',
        'examples': ['12/25/2024'],
        'extract': _extract_hartels_date
    },
    'AAA Trash Service': {
        'format': 'MM/DD/YYYY',
        'label': 'DATE (wide columnar)',
        'examples': ['10/01/2025'],
        'extract': _extract_aaa_trash_service_date
    },
    'Potties for the Rockies': {
        'format': 'M/D/YYYY',
        'label': 'Date (columnar)',
        'examples': ['9/30/2025'],
        'extract': _extract_potties_for_the_rockies_date
    },
    'Sonoco Recycling': {
        'format': 'M/D/YYYY',
        'label': 'Invoice Date: (inline)',
        'examples': ['9/26/2025'],
        'extract': _extract_sonoco_recycling_date
    },
    'Lake Area Disposal': {
        'format': 'MM/DD/YY',
        'label': 'STATEMENT DATE (columnar)',
        'examples': ['11/01/25'],
        'extract': _extract_lake_area_disposal_date
    },
    'Town of Apple Valley': {
        'format': 'MM/DD/YY',
        'label': 'BILLING DATE (wide columnar)',
        'examples': ['10/31/25'],
        'extract': _extract_town_of_apple_valley_date
    },
    'Mike Spano & Sons': {
        'format': 'M/D/YYYY',
        'label': 'Date (columnar)',
        'examples': ['9/1/2025'],
        'extract': _extract_mike_spano_and_sons_date
    },
    # --- Tranche 54 ---
    'Joseph J. Runner': {
        'format': 'M/D/YYYY',
        'label': 'Invoice Date: (wide columnar)',
        'examples': ['9/23/2025'],
        'extract': _extract_joseph_j_runner_date
    },
    'Checksammy': {
        'format': 'Mon DD, YYYY',
        'label': 'Issued (columnar)',
        'examples': ['May 01, 2025'],
        'extract': _extract_checksammy_date
    },
    'Westport Funding': {
        'format': 'MM/DD/YYYY',
        'label': 'Date (columnar)',
        'examples': ['07/15/2025'],
        'extract': _extract_westport_funding_date
    },
    'City of Quincy': {
        'format': 'MM/DD/YYYY',
        'label': 'Invoice Date: (columnar)',
        'examples': ['10/02/2025'],
        'extract': _extract_city_of_quincy_date
    },
    'Solomon Container Service': {
        'format': 'MM/DD/YYYY',
        'label': 'Date (columnar)',
        'examples': ['09/01/2025'],
        'extract': _extract_solomon_container_service_date
    },
    'Copper State Sanitation': {
        'format': 'MM/DD/YYYY',
        'label': 'DATE (columnar)',
        'examples': ['12/20/2025'],
        'extract': _extract_copper_state_sanitation_date
    },
    'Windsor Sanitation': {
        'format': 'M/D/YYYY',
        'label': 'INVOICE DATE (columnar)',
        'examples': ['9/1/2025'],
        'extract': _extract_windsor_sanitation_date
    },
    'Opdenaker Trash': {
        'format': 'MM/DD/YYYY',
        'label': 'INVOICE DATE (inline)',
        'examples': ['12/01/2025'],
        'extract': _extract_opdenaker_trash_date
    },
    'Get Rid Of It Waste': {
        'format': 'Weekday Mon DD, YYYY',
        'label': 'TrashBilling date',
        'examples': ['Mon Sep 1, 2025'],
        'extract': _extract_get_rid_of_it_waste_date
    },
    'Tri County Disposal': {
        'format': 'MM/DD/YYYY',
        'label': 'Bill Date: (wide columnar)',
        'examples': ['11/01/2025'],
        'extract': _extract_tri_county_disposal_date
    },
    'Absolute Services': {
        'format': 'MM/DD/YYYY',
        'label': 'Invoice Date: (inline)',
        'examples': ['12/01/2025'],
        'extract': _extract_absolute_services_date
    },
    'J&R Sanitation': {
        'format': 'MM/DD/YYYY',
        'label': 'DATE (inline)',
        'examples': ['09/20/2025'],
        'extract': _extract_jr_sanitation_date
    },
    # --- Tranche 55 ---
    'California Waste Recovery': {
        'format': 'MM/DD/YY',
        'label': 'Statement Date: (reverse columnar)',
        'examples': ['11/01/25'],
        'extract': _extract_california_waste_recovery_date
    },
    'MA Sanitation': {
        'format': 'MM/DD/YYYY',
        'label': 'Date (columnar)',
        'examples': ['01/21/2025'],
        'extract': _extract_ma_sanitation_date
    },
    "Kadinger's": {
        'format': 'MM/DD/YYYY',
        'label': 'DATE (wide columnar)',
        'examples': ['02/01/2025'],
        'extract': _extract_kadingers_date
    },
    'Clarke Waste Solutions': {
        'format': 'Mon DD, YYYY',
        'label': 'SERVICE DATE (columnar)',
        'examples': ['May 15, 2025'],
        'extract': _extract_clarke_waste_solutions_date
    },
    'Miller and Sons Disposal': {
        'format': 'MM/DD/YYYY',
        'label': 'Invoice date: (inline)',
        'examples': ['10/31/2025'],
        'extract': _extract_miller_and_sons_disposal_date
    },
    'Norland Environmental': {
        'format': 'M/D/YYYY',
        'label': 'Date (columnar)',
        'examples': ['2/1/2025'],
        'extract': _extract_norland_environmental_date
    },
    'Marion County Fiscal Court': {
        'format': 'M/DD/YYYY',
        'label': 'DATES OF SERVICE (inline)',
        'examples': ['7/01/2025'],
        'extract': _extract_marion_county_fiscal_court_date
    },
    'Industrial Services Lincoln': {
        'format': 'MM/DD/YYYY',
        'label': 'STATEMENT DATE (wide columnar)',
        'examples': ['08/25/2025'],
        'extract': _extract_industrial_services_lincoln_date
    },
    'City of Athens GA': {
        'format': 'M/D/YYYY',
        'label': 'DATE: (inline)',
        'examples': ['5/16/2025'],
        'extract': _extract_city_of_athens_ga_date
    },
    'Oak Disposal Services': {
        'format': 'MM/DD/YYYY',
        'label': 'DATE (inline)',
        'examples': ['11/01/2025'],
        'extract': _extract_oak_disposal_services_date
    },
    'Pederson Sanitation': {
        'format': 'Weekday Mon DD, YYYY',
        'label': 'DATE (columnar)',
        'examples': ['Thu Jul 31, 2025'],
        'extract': _extract_pederson_sanitation_date
    },
    'City of Sierra Vista': {
        'format': 'MM/DD/YYYY',
        'label': 'Bill Date (columnar)',
        'examples': ['11/07/2025'],
        'extract': _extract_city_of_sierra_vista_date
    },
    # --- Tranche 56 ---
    'Vasco Road Landfill': {
        'format': 'MM/DD/YYYY',
        'label': 'Invoice Date (inline)',
        'examples': ['09/30/2025'],
        'extract': _extract_vasco_road_landfill_date
    },
    'City of Sevierville': {
        'format': 'M/D/YYYY',
        'label': 'Billing Date (columnar)',
        'examples': ['3/21/2025'],
        'extract': _extract_city_of_sevierville_date
    },
    'Westbury Paper Stock': {
        'format': 'MM/DD/YY',
        'label': 'INV DATE (columnar)',
        'examples': ['04/27/25'],
        'extract': _extract_westbury_paper_stock_date
    },
    'Gibson Truck Service': {
        'format': 'M/D/YYYY',
        'label': 'Date (columnar)',
        'examples': ['1/10/2025'],
        'extract': _extract_gibson_truck_service_date
    },
    'City of Red Wing': {
        'format': 'MM/DD/YYYY',
        'label': 'BILLING DATE: (wide columnar)',
        'examples': ['12/17/2025'],
        'extract': _extract_city_of_red_wing_date
    },
    'Southwest Sanitation': {
        'format': 'MM/DD/YYYY',
        'label': 'Date (columnar)',
        'examples': ['10/31/2025'],
        'extract': _extract_southwest_sanitation_date
    },
    'BFI Waste': {
        'format': 'Weekday Mon DD, YYYY',
        'label': 'TrashBilling date',
        'examples': ['Wed Oct 1, 2025'],
        'extract': _extract_bfi_waste_date
    },
    'Roberts Enterprises': {
        'format': 'Weekday Mon DD, YYYY',
        'label': 'TrashBilling date',
        'examples': ['Tue Dec 2, 2025'],
        'extract': _extract_roberts_enterprises_date
    },
    'Waste Express': {
        'format': 'MM/DD/YYYY',
        'label': 'DATE (inline)',
        'examples': ['05/14/2025'],
        'extract': _extract_waste_express_date
    },
    'Snake River Rubbish': {
        'format': 'Weekday Mon DD, YYYY',
        'label': 'TrashBilling date',
        'examples': ['Sat Nov 1, 2025'],
        'extract': _extract_snake_river_rubbish_date
    },
    "Howie's Trash Service": {
        'format': 'M/DD/YY',
        'label': 'Invoice Date (wide columnar)',
        'examples': ['6/30/25'],
        'extract': _extract_howies_trash_service_date
    },
    'Satellite Shelters': {
        'format': 'MM/DD/YYYY',
        'label': 'Invoice Date: (inline)',
        'examples': ['10/23/2025'],
        'extract': _extract_satellite_shelters_date
    },
    # --- Tranche 57 ---
    'City of Buford': {
        'format': 'M/DD/YYYY',
        'label': 'Billing Date (columnar)',
        'examples': ['4/03/2025'],
        'extract': _extract_city_of_buford_date
    },
    'Orlando Recycling': {
        'format': 'Weekday Mon DD, YYYY',
        'label': 'Date: (inline)',
        'examples': ['Mon Jun 30, 2025'],
        'extract': _extract_orlando_recycling_date
    },
    "Ed's Disposal": {
        'format': 'Month DD, YYYY',
        'label': 'BILLING DATE: (inline)',
        'examples': ['October 31, 2024'],
        'extract': _extract_eds_disposal_date
    },
    'Town of Lake Park': {
        'format': 'M/D/YYYY',
        'label': 'Due Date (columnar)',
        'examples': ['8/25/2025'],
        'extract': _extract_town_of_lake_park_date
    },
    'WasteVision': {
        'format': 'MM/DD/YYYY',
        'label': 'Invoice Date : (columnar)',
        'examples': ['11/26/2024'],
        'extract': _extract_wastevision_date
    },
    'Hilltopper Refuse': {
        'format': 'M/DD/YYYY',
        'label': 'DATE (columnar)',
        'examples': ['2/03/2025'],
        'extract': _extract_hilltopper_refuse_date
    },
    'Timberline LLC': {
        'format': 'MM/DD/YYYY',
        'label': 'Date (columnar)',
        'examples': ['12/11/2025'],
        'extract': _extract_timberline_llc_date
    },
    'New Prague Sanitary': {
        'format': 'MM/DD/YYYY',
        'label': 'Invoice Date: (inline)',
        'examples': ['10/28/2025'],
        'extract': _extract_new_prague_sanitary_date
    },
    'Olcese Waste Services': {
        'format': 'M/DD/YY',
        'label': 'Invoice Date (wide columnar)',
        'examples': ['8/25/25'],
        'extract': _extract_olcese_waste_services_date
    },
    'Dillon Disposal': {
        'format': 'MM/DD/YYYY',
        'label': 'Invoice Date (columnar)',
        'examples': ['07/31/2025'],
        'extract': _extract_dillon_disposal_date
    },
    'B-N-C Trash Service': {
        'format': 'M/D/YYYY',
        'label': 'received on (TrashBilling)',
        'examples': ['9/18/2025'],
        'extract': _extract_bnc_trash_service_date
    },
    'Young Refuse': {
        'format': 'Weekday Mon DD, YYYY',
        'label': 'TrashBilling date',
        'examples': ['Tue Jan 6, 2026'],
        'extract': _extract_young_refuse_date
    },
    # --- Tranche 58 ---
    'City of Cookeville': {
        'format': 'MM/DD/YYYY',
        'label': 'Bill Date (columnar)',
        'examples': ['01/15/2025'],
        'extract': _extract_city_of_cookeville_date
    },
    'Blue Moon': {
        'format': 'Month DD, YYYY',
        'label': 'Date of issue (columnar)',
        'examples': ['January 15, 2025'],
        'extract': _extract_blue_moon_date
    },
    'Town & Country Sanitation': {
        'format': 'M/D/YYYY',
        'label': 'received on (TrashBilling)',
        'examples': ['1/15/2025'],
        'extract': _extract_town_and_country_sanitation_date
    },
    'Waste Reduction Sys': {
        'format': 'MM/DD/YYYY',
        'label': 'DATE (inline)',
        'examples': ['01/15/2025'],
        'extract': _extract_waste_reduction_sys_date
    },
    'Eastern Waste': {
        'format': 'MM/DD/YYYY',
        'label': 'Invoice Date: (inline)',
        'examples': ['01/15/2025'],
        'extract': _extract_eastern_waste_date
    },
    'Junk Solutions': {
        'format': 'Month DD, YYYY',
        'label': 'Created (inline)',
        'examples': ['January 15, 2025'],
        'extract': _extract_junk_solutions_date
    },
    'Ace Equipment Company': {
        'format': 'MM/DD/YYYY',
        'label': 'DATE (columnar)',
        'examples': ['01/15/2025'],
        'extract': _extract_ace_equipment_company_date
    },
    "Dan's Sanitation": {
        'format': 'MM/DD/YYYY',
        'label': 'Invoice Date: (inline)',
        'examples': ['01/15/2025'],
        'extract': _extract_dans_sanitation_date
    },
    "Ferrell's Disposal": {
        'format': 'M/D/YYYY',
        'label': 'Date (columnar)',
        'examples': ['1/15/2025'],
        'extract': _extract_ferrells_disposal_date
    },
    'Wayne County Utah': {
        'format': 'MM/DD/YYYY',
        'label': 'Date (columnar)',
        'examples': ['01/15/2025'],
        'extract': _extract_wayne_county_utah_date
    },
    'U & I Sanitation': {
        'format': 'Weekday Mon DD, YYYY',
        'label': 'TrashBilling date',
        'examples': ['Mon Jan 15, 2025'],
        'extract': _extract_u_and_i_sanitation_date
    },
    'C&S Disposal': {
        'format': 'Month DD, YYYY',
        'label': 'Date (columnar)',
        'examples': ['January 15, 2025'],
        'extract': _extract_c_and_s_disposal_date
    },
    # --- Tranche 59 ---
    'City of Somerset': {
        'format': 'MM/DD/YYYY',
        'label': 'SERVICE FROM (wide columnar)',
        'examples': ['03/30/2025'],
        'extract': _extract_city_of_somerset_date
    },
    'Tahoe Truckee Sierra Disposal': {
        'format': 'M/DD/YYYY',
        'label': 'INVOICE DATE (columnar)',
        'examples': ['4/30/2025'],
        'extract': _extract_tahoe_truckee_sierra_disposal_date
    },
    'Shamrock Waste': {
        'format': 'MM/DD/YYYY',
        'label': 'Invoice date: (columnar)',
        'examples': ['10/01/2025'],
        'extract': _extract_shamrock_waste_date
    },
    'City of Wolf Point': {
        'format': 'MM/DD/YYYY',
        'label': 'Billed: (inline)',
        'examples': ['01/28/2025'],
        'extract': _extract_city_of_wolf_point_date
    },
    'Lex Serv': {
        'format': 'Mon DD, YYYY',
        'label': 'Billing Date (columnar)',
        'examples': ['Apr 29, 2025'],
        'extract': _extract_lex_serv_date
    },
    'Stewart Sanitation': {
        'format': 'M/D/YYYY',
        'label': 'Invoice Date (wide columnar)',
        'examples': ['2/1/2025'],
        'extract': _extract_stewart_sanitation_date
    },
    'Humboldt County Landfill': {
        'format': 'MM/DD/YYYY',
        'label': 'DATE: (inline)',
        'examples': ['10/10/2025'],
        'extract': _extract_humboldt_county_landfill_date
    },
    'Olson Sanitation': {
        'format': 'M/D/YYYY',
        'label': 'received on (TrashBilling)',
        'examples': ['4/29/2025'],
        'extract': _extract_olson_sanitation_date
    },
    'Trash Rangers': {
        'format': 'MM/DD/YYYY',
        'label': 'Invoice Date (columnar)',
        'examples': ['11/17/2025'],
        'extract': _extract_trash_rangers_date
    },
    'Wingfield Service': {
        'format': 'Weekday Mon DD, YYYY',
        'label': 'TrashBilling date',
        'examples': ['Tue Dec 30, 2025'],
        'extract': _extract_wingfield_service_date
    },
    'A&J Trash': {
        'format': 'Weekday Mon DD, YYYY',
        'label': 'TrashBilling date',
        'examples': ['Fri Nov 21, 2025'],
        'extract': _extract_a_and_j_trash_date
    },
    'City of Rowlett': {
        'format': 'MM/DD/YYYY',
        'label': 'Bill Date (columnar)',
        'examples': ['12/30/2025'],
        'extract': _extract_city_of_rowlett_date
    },
    # --- Tranche 60 ---
    'Nisswa Sanitation': {
        'format': 'M/D/YY',
        'label': 'Invoice Date (columnar)',
        'examples': ['4/1/25'],
        'extract': _extract_nisswa_sanitation_date
    },
    'Jackson County Solid Waste': {
        'format': 'Weekday Mon DD, YYYY',
        'label': 'TrashBilling date',
        'examples': ['Mon Nov 3, 2025'],
        'extract': _extract_jackson_county_solid_waste_date
    },
    'Southeast Waste Disposal': {
        'format': 'MM/DD/YYYY',
        'label': 'Date (columnar)',
        'examples': ['6/30/2025'],
        'extract': _extract_southeast_waste_disposal_date
    },
    'Gmen Environmental': {
        'format': 'M/DD/YY',
        'label': 'Invoice Date (columnar)',
        'examples': ['7/31/25'],
        'extract': _extract_gmen_environmental_date
    },
    'City of Sidney': {
        'format': 'MM/DD/YY',
        'label': 'CYCLE DATE (columnar)',
        'examples': ['05/12/25'],
        'extract': _extract_city_of_sidney_date
    },
    'United States Disposal': {
        'format': 'M/D/YYYY',
        'label': 'Invoice Date: (inline)',
        'examples': ['11/5/2025'],
        'extract': _extract_united_states_disposal_date
    },
    'North Country Disposal': {
        'format': 'M/D/YY',
        'label': 'Date (wide columnar)',
        'examples': ['6/1/25'],
        'extract': _extract_north_country_disposal_date
    },
    'Speedy Dump': {
        'format': 'Month DD, YYYY',
        'label': 'DATE (columnar)',
        'examples': ['Dec 7, 2025'],
        'extract': _extract_speedy_dump_date
    },
    'McCullough Rubbish': {
        'format': 'MM/DD/YYYY',
        'label': 'Invoice Date: (inline)',
        'examples': ['02/10/2025'],
        'extract': _extract_mccullough_rubbish_date
    },
    'Kalamazoo Transfer Station': {
        'format': 'MM/DD/YYYY',
        'label': 'Invoice Date (inline)',
        'examples': ['07/15/2025'],
        'extract': _extract_kalamazoo_transfer_station_date
    },
    'A&C Waste Collection': {
        'format': 'MM/DD/YYYY',
        'label': 'Payment date (columnar)',
        'examples': ['07/28/2025'],
        'extract': _extract_a_and_c_waste_collection_date
    },
    'Gilton Solid Waste': {
        'format': 'M/DD/YYYY',
        'label': 'STMT DATE (inline)',
        'examples': ['1/31/2025'],
        'extract': _extract_gilton_solid_waste_date
    },
    # --- Tranche 61 ---
    'Native Dynamics': {
        'format': 'MM/DD/YYYY',
        'label': 'DATE (wide columnar)',
        'examples': ['07/31/2025'],
        'extract': _extract_native_dynamics_date
    },
    'TDS LLC': {
        'format': 'M/D/YYYY',
        'label': 'received on (TrashBilling)',
        'examples': ['10/10/2025'],
        'extract': _extract_tds_llc_date
    },
    'Bright Disposal Services': {
        'format': 'Weekday Mon DD, YYYY',
        'label': 'Date: (inline)',
        'examples': ['Sat May 10, 2025'],
        'extract': _extract_bright_disposal_services_date
    },
    'Serv-Wel Disposal': {
        'format': 'M/D/YYYY',
        'label': 'Date (columnar)',
        'examples': ['9/1/2025'],
        'extract': _extract_serv_wel_disposal_date
    },
    'City of Rockhill': {
        'format': 'Mon-DD-YYYY',
        'label': 'Due Date (columnar)',
        'examples': ['Jun-09-2025'],
        'extract': _extract_city_of_rockhill_date
    },
    'All States Services': {
        'format': 'M/D/YYYY',
        'label': 'Invoice Date: (inline)',
        'examples': ['4/1/2025'],
        'extract': _extract_all_states_services_date
    },
    'Ogborne Hauling': {
        'format': 'MM/DD/YYYY',
        'label': 'DATE (wide columnar)',
        'examples': ['06/16/2025'],
        'extract': _extract_ogborne_hauling_date
    },
    'Innovative Trash Service': {
        'format': 'Mon DD, YYYY',
        'label': 'Issued (columnar)',
        'examples': ['Jun 06, 2025'],
        'extract': _extract_innovative_trash_service_date
    },
    'Golden Valley Disposal': {
        'format': 'M/D/YYYY',
        'label': 'DATE (columnar)',
        'examples': ['6/1/2025'],
        'extract': _extract_golden_valley_disposal_date
    },
    "Guido's Services": {
        'format': 'MM/DD/YYYY',
        'label': 'DATE (columnar)',
        'examples': ['12/01/2025'],
        'extract': _extract_guidos_services_date
    },
    'Waste Masters': {
        'format': 'Mon-DD-YY',
        'label': 'DATE (reverse columnar)',
        'examples': ['Oct-18-25'],
        'extract': _extract_waste_masters_date
    },
    'Pacific Sanitation Co': {
        'format': 'MM/DD/YYYY',
        'label': 'DUE DATE (columnar)',
        'examples': ['05/10/2025'],
        'extract': _extract_pacific_sanitation_co_date
    },
    # --- Tranche 62 ---
    'Overton Recycling': {
        'format': 'M/D/YYYY',
        'label': 'received on (TrashBilling)',
        'examples': ['6/10/2025'],
        'extract': _extract_overton_recycling_date
    },
    'Helgerson Property Maintenance': {
        'format': 'MM/DD/YYYY',
        'label': 'Invoice date: (inline)',
        'examples': ['05/15/2025'],
        'extract': _extract_helgerson_property_maintenance_date
    },
    'Okon Recycling': {
        'format': 'M/D/YY',
        'label': 'Invoice Date: (reverse columnar)',
        'examples': ['5/1/25'],
        'extract': _extract_okon_recycling_date
    },
    'Waste Services Inc': {
        'format': 'MM/DD/YY',
        'label': 'INV DATE (columnar)',
        'examples': ['01/01/26'],
        'extract': _extract_waste_services_inc_date
    },
    "Fogle's": {
        'format': 'MM/DD/YYYY',
        'label': 'INVOICE DATE (columnar)',
        'examples': ['12/01/2025'],
        'extract': _extract_fogles_date
    },
    "Wayn-O's Disposal Service": {
        'format': 'M/DD/YYYY',
        'label': 'Date (columnar)',
        'examples': ['5/31/2025'],
        'extract': _extract_wayn_os_disposal_service_date
    },
    'Solid Waste Services WV': {
        'format': 'Mon-DD-YYYY',
        'label': 'INVOICE DATE (wide columnar)',
        'examples': ['Oct-31-2025'],
        'extract': _extract_solid_waste_services_wv_date
    },
    'Dyersburg Gas & Water': {
        'format': 'MM-DD-YY',
        'label': 'SERVICE FROM (columnar)',
        'examples': ['04-16-25'],
        'extract': _extract_dyersburg_gas_and_water_date
    },
    'Volunteer Disposal West': {
        'format': 'Weekday Mon DD, YYYY',
        'label': 'TrashBilling date',
        'examples': ['Mon Dec 1, 2025'],
        'extract': _extract_volunteer_disposal_west_date
    },
    'Certified Enterprises': {
        'format': 'MM/DD/YYYY',
        'label': 'Inv Date (wide columnar)',
        'examples': ['12/15/2025'],
        'extract': _extract_certified_enterprises_date
    },
    'Becker Complete': {
        'format': 'MM/DD/YYYY',
        'label': 'DATE (columnar)',
        'examples': ['07/01/2025'],
        'extract': _extract_becker_complete_date
    },
    'Reliable Paper': {
        'format': 'M/D/YYYY',
        'label': 'Invoice Date (report format)',
        'examples': ['3/1/2025'],
        'extract': _extract_reliable_paper_date
    },
    # --- Tranche 63 ---
    'Skyhook': {
        'format': 'MM/DD/YYYY',
        'label': 'Invoice date: (inline)',
        'examples': ['07/22/2025'],
        'extract': _extract_skyhook_date
    },
    'City of Fort Myers': {
        'format': 'MM/DD/YY',
        'label': 'BILL DATE: (inline)',
        'examples': ['07/17/25'],
        'extract': _extract_city_of_fort_myers_date
    },
    'City of Douglasville': {
        'format': 'MM/DD/YY',
        'label': 'DUE DATE (columnar)',
        'examples': ['07/01/25'],
        'extract': _extract_city_of_douglasville_date
    },
    'Kopchos Sanitation': {
        'format': 'MM/DD/YYYY',
        'label': 'STATEMENT DATE (columnar)',
        'examples': ['05/31/2025'],
        'extract': _extract_kopchos_sanitation_date
    },
    'Metech Recycling': {
        'format': 'MM/DD/YYYY',
        'label': 'DATE (inline)',
        'examples': ['11/10/2025'],
        'extract': _extract_metech_recycling_date
    },
    'Madden Sanitation': {
        'format': 'M/D/YYYY',
        'label': 'received on (TrashBilling)',
        'examples': ['3/6/2025'],
        'extract': _extract_madden_sanitation_date
    },
    'American Eagle Waste': {
        'format': 'MM/DD/YY',
        'label': 'BILL DATE (columnar)',
        'examples': ['03/01/25'],
        'extract': _extract_american_eagle_waste_date
    },
    'Reno Forklift': {
        'format': 'MM/DD/YYYY',
        'label': 'Statement Date (columnar)',
        'examples': ['03/03/2025'],
        'extract': _extract_reno_forklift_date
    },
    'DC Waste': {
        'format': 'M/D/YY',
        'label': 'Invoice Date (columnar)',
        'examples': ['11/1/25'],
        'extract': _extract_dc_waste_date
    },
    'South San Francisco Scavenger': {
        'format': 'M/D/YYYY',
        'label': 'Invoice Date (columnar)',
        'examples': ['1/1/2026'],
        'extract': _extract_south_san_francisco_scavenger_date
    },
    "Shular's Trash Service": {
        'format': 'Weekday Mon DD, YYYY',
        'label': 'DATE (columnar)',
        'examples': ['Mon Jun 23, 2025'],
        'extract': _extract_shulars_trash_service_date
    },
    'Nooksack Valley Disposal': {
        'format': 'MM/DD/YY',
        'label': 'Billing Date: (inline)',
        'examples': ['11/30/25'],
        'extract': _extract_nooksack_valley_disposal_date
    },
    # --- Tranche 64 ---
    'Hiltz': {
        'format': 'Mon-DD-YY',
        'label': 'DATE (columnar)',
        'examples': ['May-01-25'],
        'extract': _extract_hiltz_date
    },
    'City of Willcox': {
        'format': 'MM-DD-YYYY',
        'label': 'Billing Date (wide columnar)',
        'examples': ['05-31-2025'],
        'extract': _extract_city_of_willcox_date
    },
    'Anchor Technical': {
        'format': 'M/DD/YYYY',
        'label': 'Date (columnar)',
        'examples': ['9/18/2025'],
        'extract': _extract_anchor_technical_date
    },
    "Clark's Disposal": {
        'format': 'Weekday Mon DD, YYYY',
        'label': 'TrashBilling date',
        'examples': ['Wed May 28, 2025'],
        'extract': _extract_clarks_disposal_date
    },
    'Missoula Compost': {
        'format': 'M/D/YYYY',
        'label': 'received on (TrashBilling)',
        'examples': ['9/25/2025'],
        'extract': _extract_missoula_compost_date
    },
    'Recycling Center of North Dakota': {
        'format': 'M/DD/YYYY',
        'label': 'Date (columnar)',
        'examples': ['2/28/2025'],
        'extract': _extract_recycling_center_of_north_dakota_date
    },
    'Gear For Waste': {
        'format': 'M/D/YYYY',
        'label': 'Date (columnar)',
        'examples': ['1/1/2026'],
        'extract': _extract_gear_for_waste_date
    },
    'Tom Danley Disposal': {
        'format': 'MM/DD/YYYY',
        'label': 'DATE (columnar)',
        'examples': ['10/27/2025'],
        'extract': _extract_tom_danley_disposal_date
    },
    'Triple H Enterprises': {
        'format': 'M/D/YYYY',
        'label': 'Date (columnar)',
        'examples': ['9/1/2025'],
        'extract': _extract_triple_h_enterprises_date
    },
    'Waste Disposal AZ': {
        'format': 'MM/DD/YYYY',
        'label': 'Date Billed: (inline)',
        'examples': ['12/04/2025'],
        'extract': _extract_waste_disposal_az_date
    },
    'Kirby Sanitation': {
        'format': 'M/DD/YYYY',
        'label': 'INVOICE DATE (columnar)',
        'examples': ['3/31/2025'],
        'extract': _extract_kirby_sanitation_date
    },
    'Winston Sanitary': {
        'format': 'MM/DD/YYYY',
        'label': 'STATEMENT DATE (columnar)',
        'examples': ['04/30/2025'],
        'extract': _extract_winston_sanitary_date
    },
    # --- Tranche 65 ---
    'Top of the Line Dumpsters': {
        'format': 'M/D/YYYY',
        'label': 'Invoice Date (columnar)',
        'examples': ['12/1/2025'],
        'extract': _extract_top_of_the_line_dumpsters_date
    },
    'Chisago Lakes Sanitation': {
        'format': 'MM/DD/YY',
        'label': 'INV DATE (columnar)',
        'examples': ['05/31/25'],
        'extract': _extract_chisago_lakes_sanitation_date
    },
    'Dedicated Dumpster Service': {
        'format': 'Weekday Mon DD, YYYY',
        'label': 'Date: (inline)',
        'examples': ['Tue Oct 28, 2025'],
        'extract': _extract_dedicated_dumpster_service_date
    },
    'Citrus County Utilities': {
        'format': 'MM/DD/YYYY',
        'label': 'Invoice Date: (wide columnar)',
        'examples': ['03/31/2025'],
        'extract': _extract_citrus_county_utilities_date
    },
    'Pendleton Sanitary Service': {
        'format': 'MM/DD/YYYY',
        'label': 'STATEMENT DATE (columnar)',
        'examples': ['09/30/2025'],
        'extract': _extract_pendleton_sanitary_service_date
    },
    'United Waste Systems': {
        'format': 'MM/DD/YYYY',
        'label': 'Invoice Date: (columnar)',
        'examples': ['04/07/2025'],
        'extract': _extract_united_waste_systems_date
    },
    'Cogent Waste Solutions': {
        'format': 'M/D/YY',
        'label': 'Invoice Date (reverse columnar)',
        'examples': ['12/1/25'],
        'extract': _extract_cogent_waste_solutions_date
    },
    'GTX Gainsborough Waste': {
        'format': 'M/D/YYYY',
        'label': 'Date (columnar)',
        'examples': ['10/1/2024'],
        'extract': _extract_gtx_gainsborough_waste_date
    },
    'Waste Disposal Services': {
        'format': 'M/D/YYYY',
        'label': 'received on (TrashBilling)',
        'examples': ['11/30/2025'],
        'extract': _extract_waste_disposal_services_date
    },
    'Town of Gardnerville': {
        'format': 'MM/DD/YY',
        'label': 'DATE MAILED (columnar)',
        'examples': ['06/01/25'],
        'extract': _extract_town_of_gardnerville_date
    },
    'Step Up Disposals': {
        'format': 'MM/DD/YYYY',
        'label': 'Invoice Date: (inline)',
        'examples': ['03/15/2025'],
        'extract': _extract_step_up_disposals_date
    },
    'City of Madisonville': {
        'format': 'M/DD/YY',
        'label': 'Billing Date (columnar)',
        'examples': ['9/02/25'],
        'extract': _extract_city_of_madisonville_date
    },
    # --- Tranche 66 ---
    'Valley Waste Service': {
        'format': 'MM/DD/YYYY',
        'label': 'Invoice Date: (inline)',
        'examples': ['05/01/2025'],
        'extract': _extract_valley_waste_service_date
    },
    'Salt River Pima': {
        'format': 'MM/DD/YYYY',
        'label': 'Invoice Date (columnar)',
        'examples': ['10/31/2025'],
        'extract': _extract_salt_river_pima_date
    },
    'Best Pick Disposal': {
        'format': 'MM/DD/YYYY',
        'label': 'INVOICE DATE (inline)',
        'examples': ['10/23/2025'],
        'extract': _extract_best_pick_disposal_date
    },
    'National Waste & Disposal': {
        'format': 'M/D/YYYY',
        'label': 'INVOICE DATE (columnar)',
        'examples': ['8/31/2025'],
        'extract': _extract_national_waste_and_disposal_date
    },
    'MDS Waste': {
        'format': 'Weekday Mon DD, YYYY',
        'label': 'TrashBilling format',
        'examples': ['Mon Dec 1, 2025'],
        'extract': _extract_mds_waste_date
    },
    "Abe's Trash Service": {
        'format': 'MM/DD/YY',
        'label': 'Invoice Date (reverse columnar)',
        'examples': ['11/25/25'],
        'extract': _extract_abes_trash_service_date
    },
    'Island Refuse': {
        'format': 'MM/DD/YYYY',
        'label': 'DATE (inline)',
        'examples': ['12/31/2024'],
        'extract': _extract_island_refuse_date
    },
    'City of Dickinson': {
        'format': 'Month DD, YYYY',
        'label': 'BILLING START DATE (columnar)',
        'examples': ['Jan 21, 2025'],
        'extract': _extract_city_of_dickinson_date
    },
    'Snake River Dispose-All': {
        'format': 'M/D/YYYY',
        'label': 'Date (columnar)',
        'examples': ['12/6/2025'],
        'extract': _extract_snake_river_dispose_all_date
    },
    'Maui Disposal Co': {
        'format': 'Month DD, YYYY',
        'label': 'Payment Date (columnar)',
        'examples': ['August 07, 2025'],
        'extract': _extract_maui_disposal_co_date
    },
    "Matt's Sanitation": {
        'format': 'MM-DD-YYYY',
        'label': 'STATEMENT (inline)',
        'examples': ['12-31-2025'],
        'extract': _extract_matts_sanitation_date
    },
    'Hughes & Sons': {
        'format': 'MM/DD/YYYY',
        'label': 'Invoice Date: (columnar)',
        'examples': ['12/03/2024'],
        'extract': _extract_hughes_and_sons_date
    },
    # --- Tranche 67 ---
    'CompostNow': {
        'format': 'MM/DD/YYYY',
        'label': 'DATE (columnar)',
        'examples': ['02/06/2025'],
        'extract': _extract_compostnow_date
    },
    "Martin's Trash Service": {
        'format': 'Weekday Mon DD, YYYY',
        'label': 'TrashBilling format',
        'examples': ['Tue Jul 22, 2025'],
        'extract': _extract_martins_trash_service_date
    },
    'Brothers Disposal': {
        'format': 'M/DD/YYYY',
        'label': 'received on (TrashBilling)',
        'examples': ['4/29/2025'],
        'extract': _extract_brothers_disposal_date
    },
    'Sutherlin Sanitary': {
        'format': 'Month DD, YYYY',
        'label': 'Bill Date (columnar)',
        'examples': ['June 24, 2025'],
        'extract': _extract_sutherlin_sanitary_date
    },
    'Goode Companies': {
        'format': 'MM/DD/YY',
        'label': 'INV DATE (columnar)',
        'examples': ['12/31/24'],
        'extract': _extract_goode_companies_date
    },
    'Cressman Sanitation': {
        'format': 'Weekday Mon DD, YYYY',
        'label': 'TrashBilling format',
        'examples': ['Fri Aug 1, 2025'],
        'extract': _extract_cressman_sanitation_date
    },
    'Sonoran Ranch': {
        'format': 'Mon D, YYYY',
        'label': 'Issued Date: (columnar)',
        'examples': ['Apr 1, 2025'],
        'extract': _extract_sonoran_ranch_date
    },
    'Franklin Pallet': {
        'format': 'DD Month YYYY',
        'label': 'Invoice Date: (inline)',
        'examples': ['21 November 2025'],
        'extract': _extract_franklin_pallet_date
    },
    'City of Culver City': {
        'format': 'Month DD, YYYY',
        'label': 'header date',
        'examples': ['July 1, 2025'],
        'extract': _extract_city_of_culver_city_date
    },
    'Garland County Landfill': {
        'format': 'MM/DD/YYYY',
        'label': 'Invoice Date: (inline)',
        'examples': ['03/31/2025'],
        'extract': _extract_garland_county_landfill_date
    },
    'Olathe Kansas': {
        'format': 'MM/DD/YYYY',
        'label': 'Statement Date (columnar)',
        'examples': ['10/30/2025'],
        'extract': _extract_olathe_kansas_date
    },
    'R & R Midwest': {
        'format': 'MM/DD/YYYY',
        'label': 'DATE (inline)',
        'examples': ['09/24/2025'],
        'extract': _extract_r_and_r_midwest_date
    },
    # --- Tranche 68 ---
    'Ingrum Waste Disposal': {
        'format': 'Mon-DD-YY',
        'label': 'DATE (reverse columnar)',
        'examples': ['Jun-30-25'],
        'extract': _extract_ingrum_waste_disposal_date
    },
    'Impact Environmental': {
        'format': 'M/DD/YYYY',
        'label': 'header date',
        'examples': ['2/25/2025'],
        'extract': _extract_impact_environmental_date
    },
    'Jamaica Ash & Rubbish': {
        'format': 'MM/DD/YY',
        'label': 'INV DATE (columnar)',
        'examples': ['08/31/25'],
        'extract': _extract_jamaica_ash_and_rubbish_date
    },
    'Capital City': {
        'format': 'MM/DD/YYYY',
        'label': 'Invoice Date: (columnar)',
        'examples': ['07/10/2025'],
        'extract': _extract_capital_city_date
    },
    'AB-8 Waste Solutions': {
        'format': 'M/D/YYYY',
        'label': 'Date (columnar)',
        'examples': ['6/20/2025'],
        'extract': _extract_ab_8_waste_solutions_date
    },
    'Alameda County Industries': {
        'format': 'MM/DD/YYYY',
        'label': 'INV. DATE (columnar)',
        'examples': ['11/30/2025'],
        'extract': _extract_alameda_county_industries_date
    },
    'Minnkota Recycling': {
        'format': 'M/DD/YYYY',
        'label': 'Invoice Date (columnar)',
        'examples': ['5/31/2025'],
        'extract': _extract_minnkota_recycling_date
    },
    'CTL 3R Technology': {
        'format': 'MM/DD/YYYY',
        'label': 'DATE (columnar)',
        'examples': ['10/31/2025'],
        'extract': _extract_ctl_3r_technology_date
    },
    'City of Grand Junction': {
        'format': 'MM/DD/YYYY',
        'label': 'Trash Service (columnar)',
        'examples': ['01/31/2025'],
        'extract': _extract_city_of_grand_junction_date
    },
    'City of Del Rio': {
        'format': 'MM/DD/YYYY',
        'label': 'Due Date (columnar)',
        'examples': ['08/22/2025'],
        'extract': _extract_city_of_del_rio_date
    },
    'A&I Pallets': {
        'format': 'MM/DD/YYYY',
        'label': 'DATE (columnar)',
        'examples': ['12/15/2025'],
        'extract': _extract_a_and_i_pallets_date
    },
    'Chris Rizzo Trucking': {
        'format': 'M/D/YYYY',
        'label': 'received on (TrashBilling)',
        'examples': ['12/4/2025'],
        'extract': _extract_chris_rizzo_trucking_date
    },
    # --- Tranche 69 ---
    "Wright's Environmental": {
        'format': 'Weekday Mon DD, YYYY',
        'label': 'TrashBilling format',
        'examples': ['Tue Sep 23, 2025'],
        'extract': _extract_wrights_environmental_date
    },
    'Timmons Waste Service': {
        'format': 'MM/DD/YYYY',
        'label': 'Invoice Date (columnar)',
        'examples': ['12/31/2024'],
        'extract': _extract_timmons_waste_service_date
    },
    'City of Dumas': {
        'format': 'M/D/YYYY',
        'label': 'Bill Date (columnar)',
        'examples': ['6/9/2025'],
        'extract': _extract_city_of_dumas_date
    },
    'Coles County Sanitation': {
        'format': 'Weekday Mon DD, YYYY',
        'label': 'TrashBilling format',
        'examples': ['Tue Sep 2, 2025'],
        'extract': _extract_coles_county_sanitation_date
    },
    'Mountain Disposal Inc': {
        'format': 'Weekday Mon DD, YYYY',
        'label': 'TrashBilling format',
        'examples': ['Mon Dec 1, 2025'],
        'extract': _extract_mountain_disposal_inc_date
    },
    'Panola County Solid Waste': {
        'format': 'MM/DD/YY',
        'label': 'DUE DATE (inline)',
        'examples': ['11/15/25'],
        'extract': _extract_panola_county_solid_waste_date
    },
    "Dayne's Waste Disposal": {
        'format': 'M/DD/YYYY',
        'label': 'Date (columnar)',
        'examples': ['5/20/2025'],
        'extract': _extract_daynes_waste_disposal_date
    },
    'Pratt Recycling': {
        'format': 'Mon-DD-YY',
        'label': 'DATE (columnar)',
        'examples': ['Mar-26-25'],
        'extract': _extract_pratt_recycling_date
    },
    'City of Vinita': {
        'format': 'M/D/YYYY',
        'label': 'Transaction Time (inline)',
        'examples': ['3/3/2025'],
        'extract': _extract_city_of_vinita_date
    },
    'Clackamas Garbage': {
        'format': 'Month DD, YYYY',
        'label': 'Bill Date (inline)',
        'examples': ['December 31, 2025'],
        'extract': _extract_clackamas_garbage_date
    },
    'Delta Garbage Service': {
        'format': 'M/D/YYYY',
        'label': 'Date (columnar)',
        'examples': ['12/1/2025'],
        'extract': _extract_delta_garbage_service_date
    },
    'Roseburg Disposal': {
        'format': 'MM/DD/YYYY',
        'label': 'DATE (columnar)',
        'examples': ['07/31/2025'],
        'extract': _extract_roseburg_disposal_date
    },
    # --- Tranche 70 ---
    'Waste Removal & Recycling': {
        'format': 'M/DD/YYYY',
        'label': 'Date (columnar)',
        'examples': ['7/21/2025'],
        'extract': _extract_waste_removal_and_recycling_date
    },
    'Westside Disposal': {
        'format': 'MM/DD/YYYY',
        'label': 'Payment date (columnar)',
        'examples': ['12/29/2025'],
        'extract': _extract_westside_disposal_date
    },
    'Palm Springs Disposal': {
        'format': 'Month YYYY',
        'label': 'BILLING PERIOD (columnar)',
        'examples': ['APRIL 2025'],
        'extract': _extract_palm_springs_disposal_date
    },
    'Tacoma Public Utilities': {
        'format': 'MM/DD/YYYY',
        'label': 'Date: (inline)',
        'examples': ['07/03/2025'],
        'extract': _extract_tacoma_public_utilities_date
    },
    'South Plains Waste': {
        'format': 'M/DD/YYYY',
        'label': 'DATE (columnar)',
        'examples': ['5/26/2025'],
        'extract': _extract_south_plains_waste_date
    },
    'EarthSavers': {
        'format': 'Month D, YYYY',
        'label': 'Invoice Date: (columnar)',
        'examples': ['November 1, 2025'],
        'extract': _extract_earthsavers_date
    },
    'Brannon Industrial': {
        'format': 'Mon DD, YYYY',
        'label': 'DATE (columnar)',
        'examples': ['Jun 30, 2025'],
        'extract': _extract_brannon_industrial_date
    },
    'Centre Water Works': {
        'format': 'MM/DD/YY',
        'label': 'BILL DATE (columnar)',
        'examples': ['12/22/25'],
        'extract': _extract_centre_water_works_date
    },
    'Scraps Compost': {
        'format': 'Month DD, YYYY',
        'label': 'Date paid (inline)',
        'examples': ['October 15, 2025'],
        'extract': _extract_scraps_compost_date
    },
    'Niese Hauling': {
        'format': 'MM/DD/YYYY',
        'label': 'Invoice date: (inline)',
        'examples': ['11/21/2025'],
        'extract': _extract_niese_hauling_date
    },
    'DC Metals': {
        'format': 'M/D/YYYY',
        'label': 'Date (columnar)',
        'examples': ['9/2/2025'],
        'extract': _extract_dc_metals_date
    },
    'Empire Disposal': {
        'format': 'MM/DD/YYYY',
        'label': 'STATEMENT DATE (columnar)',
        'examples': ['11/28/2025'],
        'extract': _extract_empire_disposal_date
    },
    # --- Tranche 71 ---
    'City of Cartersville': {
        'format': 'Mon D, YYYY',
        'label': 'Billing Date (columnar)',
        'examples': ['Oct 8, 2025'],
        'extract': _extract_city_of_cartersville_date
    },
    'City of Gainesville TX': {
        'format': 'MM/DD/YYYY',
        'label': 'BILL DATE (columnar)',
        'examples': ['10/31/2025'],
        'extract': _extract_city_of_gainesville_tx_date
    },
    'City of Fort Smith': {
        'format': 'MM/DD/YYYY',
        'label': 'Due Date (columnar)',
        'examples': ['05/27/2025'],
        'extract': _extract_city_of_fort_smith_date
    },
    "Loren's Sanitation": {
        'format': 'M/DD/YY',
        'label': 'CLOSING DATE (columnar)',
        'examples': ['7/31/25'],
        'extract': _extract_lorens_sanitation_date
    },
    'Weiner Iron & Metal': {
        'format': 'M/D/YYYY',
        'label': 'Invoice Date: (inline)',
        'examples': ['12/3/2025'],
        'extract': _extract_weiner_iron_and_metal_date
    },
    'BestTrash': {
        'format': 'Mon D, YYYY',
        'label': 'DATE (columnar)',
        'examples': ['Sep 1, 2025'],
        'extract': _extract_besttrash_date
    },
    'C&C Disposal': {
        'format': 'MM/DD/YYYY',
        'label': 'INVOICE DATE (inline)',
        'examples': ['09/01/2025'],
        'extract': _extract_c_and_c_disposal_date
    },
    'Chum Refuse': {
        'format': 'MM/DD/YYYY',
        'label': 'Invoice Date (columnar)',
        'examples': ['06/02/2025'],
        'extract': _extract_chum_refuse_date
    },
    'Sustainable Environmental Management': {
        'format': 'M/DD/YYYY',
        'label': 'DATE: (columnar)',
        'examples': ['3/10/2025'],
        'extract': _extract_sustainable_environmental_management_date
    },
    'Main Street Fibers': {
        'format': 'MM/DD/YY',
        'label': 'Invoice Date (columnar)',
        'examples': ['11/01/25'],
        'extract': _extract_main_street_fibers_date
    },
    'City of Lompoc': {
        'format': 'MM/DD/YYYY',
        'label': 'Due Date (inline)',
        'examples': ['09/09/2025'],
        'extract': _extract_city_of_lompoc_date
    },
    'Emery County Sanitation': {
        'format': 'Mon DD, YYYY',
        'label': 'Statement Date: (inline)',
        'examples': ['Jun 30, 2025'],
        'extract': _extract_emery_county_sanitation_date
    },
    # --- Tranche 72 ---
    'Elecke': {
        'format': 'MM/DD/YYYY',
        'label': 'Date (columnar)',
        'examples': ['11/30/2025'],
        'extract': _extract_elecke_date
    },
    'AMG Resources': {
        'format': 'MM/DD/YYYY',
        'label': 'INVOICE DATE: (inline)',
        'examples': ['12/01/2025'],
        'extract': _extract_amg_resources_date
    },
    'Sunny Trash Hauling': {
        'format': 'Mon DD, YYYY',
        'label': 'INVOICE DATE (columnar)',
        'examples': ['Dec 11, 2025'],
        'extract': _extract_sunny_trash_hauling_date
    },
    'American Reclamation': {
        'format': 'M/D/YY',
        'label': 'Invoice Date (columnar)',
        'examples': ['9/1/25'],
        'extract': _extract_american_reclamation_date
    },
    'MSC Industries': {
        'format': 'MM/DD/YYYY',
        'label': 'DATE (reverse columnar)',
        'examples': ['01/31/2025'],
        'extract': _extract_msc_industries_date
    },
    'American Resource Management': {
        'format': 'M/D/YYYY',
        'label': 'Date (columnar)',
        'examples': ['4/5/2025'],
        'extract': _extract_american_resource_management_date
    },
    'IROW': {
        'format': 'Mon DD, YYYY',
        'label': 'Invoice Date: (columnar)',
        'examples': ['Oct 31, 2025'],
        'extract': _extract_irow_date
    },
    'Agri-Cycle': {
        'format': 'DD-Mon-YYYY',
        'label': 'DATE (columnar)',
        'examples': ['30-Sep-2025'],
        'extract': _extract_agri_cycle_date
    },
    'Friends Garbage': {
        'format': 'MM/DD/YYYY',
        'label': 'transaction date',
        'examples': ['06/02/2025'],
        'extract': _extract_friends_garbage_date
    },
    "Brandt's Sanitary": {
        'format': 'MM/DD/YYYY',
        'label': 'DATE (columnar)',
        'examples': ['01/31/2025'],
        'extract': _extract_brandts_sanitary_date
    },
    'City of Durant': {
        'format': 'M/DD/YYYY',
        'label': 'Due Date (columnar)',
        'examples': ['8/26/2025'],
        'extract': _extract_city_of_durant_date
    },
    'Watertown Iron': {
        'format': 'MM/DD/YYYY',
        'label': 'Inv Date: (inline)',
        'examples': ['12/01/2025'],
        'extract': _extract_watertown_iron_date
    },
    # --- Tranche 73 ---
    'Top Dog Waste': {
        'format': 'Mon DD, YYYY',
        'label': 'DATE (columnar)',
        'examples': ['Dec 15, 2025'],
        'extract': _extract_top_dog_waste_date
    },
    "Kurtzman's Sanitation": {
        'format': 'M/DD/YYYY',
        'label': 'Date (columnar)',
        'examples': ['1/31/2025'],
        'extract': _extract_kurtzmans_sanitation_date
    },
    'Central Valley Disposal': {
        'format': 'M/DD/YYYY',
        'label': 'Date (inline)',
        'examples': ['1/15/2025'],
        'extract': _extract_central_valley_disposal_date
    },
    'Mulberry Ventures': {
        'format': 'M/DD/YYYY',
        'label': 'DATE (columnar)',
        'examples': ['6/30/2025'],
        'extract': _extract_mulberry_ventures_date
    },
    'Green Environmental Services': {
        'format': 'MM/DD/YYYY',
        'label': 'DATE (columnar - transaction)',
        'examples': ['09/25/2025'],
        'extract': _extract_green_environmental_services_date
    },
    'Federal Recycling & Waste Solutions': {
        'format': 'MM/DD/YYYY',
        'label': 'DATE (columnar)',
        'examples': ['12/31/2025'],
        'extract': _extract_federal_recycling_and_waste_solutions_date
    },
    'Old West Disposal': {
        'format': 'MM/DD/YYYY',
        'label': 'DATE (columnar)',
        'examples': ['11/30/2025'],
        'extract': _extract_old_west_disposal_date
    },
    'City of Colby': {
        'format': 'M/DD/YYYY',
        'label': 'Billing Date (columnar)',
        'examples': ['9/01/2025'],
        'extract': _extract_city_of_colby_date
    },
    'Mavilyn Industries': {
        'format': 'MM/DD/YYYY',
        'label': 'DATE (reverse columnar)',
        'examples': ['12/15/2025'],
        'extract': _extract_mavilyn_industries_date
    },
    'J & S Trash Collection': {
        'format': 'Weekday Mon DD, YYYY',
        'label': 'TrashBilling format',
        'examples': ['Wed Dec 11, 2025'],
        'extract': _extract_j_and_s_trash_collection_date
    },
    'Commonwealth Waste Solutions': {
        'format': 'M/DD/YYYY',
        'label': 'Date (columnar)',
        'examples': ['6/30/2025'],
        'extract': _extract_commonwealth_waste_solutions_date
    },
    'Canusa Hershman': {
        'format': 'Mon D, YYYY',
        'label': 'date after invoice number',
        'examples': ['Oct 1, 2025'],
        'extract': _extract_canusa_hershman_date
    },
    # --- Tranche 74 ---
    'Kings Roll-Off': {
        'format': 'M/D/YYYY',
        'label': 'Invoice Date: (inline)',
        'examples': ['09/5/2025'],
        'extract': _extract_kings_roll_off_date
    },
    'Dallas Recycling': {
        'format': 'MM/DD/YYYY',
        'label': 'DATE (columnar)',
        'examples': ['02/28/2025'],
        'extract': _extract_dallas_recycling_date
    },
    'CWSI': {
        'format': 'M/D/YY',
        'label': 'Date: or standalone',
        'examples': ['9/1/25'],
        'extract': _extract_cwsi_date
    },
    'Edge Waste': {
        'format': 'Weekday Mon D, YYYY',
        'label': 'TrashBilling format',
        'examples': ['Mon Dec 8, 2025'],
        'extract': _extract_edge_waste_date
    },
    'Wasteless Solutions': {
        'format': 'MM/DD/YYYY',
        'label': 'DATE (columnar)',
        'examples': ['11/01/2025'],
        'extract': _extract_wasteless_solutions_date
    },
    'Hometown Disposal': {
        'format': 'MM/DD/YYYY',
        'label': 'DATE (columnar, wide)',
        'examples': ['08/31/2025'],
        'extract': _extract_hometown_disposal_date
    },
    'Smoky Mountain Waste': {
        'format': 'M/D/YYYY',
        'label': 'Date (columnar)',
        'examples': ['10/1/2025'],
        'extract': _extract_smoky_mountain_waste_date
    },
    'Allied Recycling': {
        'format': 'M/D/YYYY',
        'label': 'Date (columnar, wide)',
        'examples': ['7/2/2025'],
        'extract': _extract_allied_recycling_date
    },
    'Enviromax Recycling': {
        'format': 'MM/DD/YYYY',
        'label': 'DATE (columnar, wide)',
        'examples': ['05/01/2025'],
        'extract': _extract_enviromax_recycling_date
    },
    'City of Kirkland': {
        'format': 'MM/DD/YYYY',
        'label': 'Bill Date (columnar)',
        'examples': ['11/12/2025'],
        'extract': _extract_city_of_kirkland_date
    },
    'Loren Fischer Disposal': {
        'format': 'Weekday Mon D, YYYY',
        'label': 'TrashBilling format',
        'examples': ['Wed Dec 31, 2025'],
        'extract': _extract_loren_fischer_disposal_date
    },
    'Pluffmud Recycling': {
        'format': 'M/D/YYYY',
        'label': 'INVOICE header then date',
        'examples': ['9/1/2025'],
        'extract': _extract_pluffmud_recycling_date
    },
    # --- Tranche 75 ---
    'Yreka Transfer': {
        'format': 'MM/DD/YYYY',
        'label': 'Transaction Date: (columnar)',
        'examples': ['07/15/2025'],
        'extract': _extract_yreka_transfer_date
    },
    'Monterey City Disposal': {
        'format': 'M/DD/YYYY',
        'label': 'INVOICE DATE (columnar)',
        'examples': ['4/30/2025'],
        'extract': _extract_monterey_city_disposal_date
    },
    'Break It Down': {
        'format': 'MM/DD/YYYY',
        'label': 'Invoice date: (inline)',
        'examples': ['07/01/2025'],
        'extract': _extract_break_it_down_date
    },
    'North Lincoln Sanitary': {
        'format': 'Month DD, YYYY',
        'label': 'Bill Date (columnar)',
        'examples': ['March 5, 2025'],
        'extract': _extract_north_lincoln_sanitary_date
    },
    'Ace Sanitation Service': {
        'format': 'M/DD/YYYY',
        'label': 'received on (TrashBilling)',
        'examples': ['10/17/2025'],
        'extract': _extract_ace_sanitation_service_date
    },
    'All States Rentals': {
        'format': 'M/D/YYYY',
        'label': 'Invoice Date: (columnar)',
        'examples': ['11/1/2025'],
        'extract': _extract_all_states_rentals_date
    },
    'Breezy Hollow': {
        'format': 'MM-D-YY',
        'label': 'DATE (inline)',
        'examples': ['12-5-25'],
        'extract': _extract_breezy_hollow_date
    },
    'City of Largo': {
        'format': 'MM/DD/YY',
        'label': 'Bill Date (columnar)',
        'examples': ['01/31/25'],
        'extract': _extract_city_of_largo_date
    },
    'C Stoneham': {
        'format': 'Mon DD, YYYY',
        'label': 'Invoice Date: (inline)',
        'examples': ['Jun 20, 2025'],
        'extract': _extract_c_stoneham_date
    },
    'Georgetown Paper Stock': {
        'format': 'MM/DD/YYYY',
        'label': 'DATE (columnar)',
        'examples': ['02/28/2025'],
        'extract': _extract_georgetown_paper_stock_date
    },
    'Malcom Enterprises': {
        'format': 'Weekday Mon DD, YYYY',
        'label': 'TrashBilling format',
        'examples': ['Wed Nov 26, 2025'],
        'extract': _extract_malcom_enterprises_date
    },
    'Reddy Rentals': {
        'format': 'MM/DD/YYYY',
        'label': 'Date (columnar)',
        'examples': ['12/31/2025'],
        'extract': _extract_reddy_rentals_date
    },
    # --- Tranche 76 ---
    'City of Tullahoma': {
        'format': 'MM/DD/YYYY',
        'label': 'Statement Date (columnar)',
        'examples': ['04/01/2025'],
        'extract': _extract_city_of_tullahoma_date
    },
    'Davis Disposal': {
        'format': 'MM/DD/YYYY',
        'label': 'Invoice date: (columnar)',
        'examples': ['07/15/2025'],
        'extract': _extract_davis_disposal_date
    },
    'Crown Waste & Recycling': {
        'format': 'MM/DD/YY',
        'label': 'Date (inline)',
        'examples': ['08/01/25'],
        'extract': _extract_crown_waste_and_recycling_date
    },
    'Standing Rock Sanitation': {
        'format': 'M/DD/YYYY',
        'label': 'DATE (columnar, wide)',
        'examples': ['3/31/2025'],
        'extract': _extract_standing_rock_sanitation_date
    },
    'SOS Waste Disposal': {
        'format': 'MM/DD/YYYY',
        'label': 'Invoice date: (inline)',
        'examples': ['12/03/2025'],
        'extract': _extract_sos_waste_disposal_date
    },
    'City & Lakes Disposal': {
        'format': 'MM/DD/YY',
        'label': 'INV DATE (columnar)',
        'examples': ['06/01/25'],
        'extract': _extract_city_and_lakes_disposal_date
    },
    "Adam's Disposal": {
        'format': 'Mon D, YYYY',
        'label': 'Issued Date: (columnar)',
        'examples': ['Aug 8, 2025'],
        'extract': _extract_adams_disposal_date
    },
    'Golden Eagle Services': {
        'format': 'MM/DD/YYYY',
        'label': 'Invoice Date (columnar)',
        'examples': ['01/31/2025'],
        'extract': _extract_golden_eagle_services_date
    },
    'Hamilton Recycling Disposal': {
        'format': 'Weekday Mon DD, YYYY',
        'label': 'TrashBilling format',
        'examples': ['Wed Aug 27, 2025'],
        'extract': _extract_hamilton_recycling_disposal_date
    },
    'MaxShred': {
        'format': 'MM/DD/YYYY',
        'label': 'Invoice Date: (inline)',
        'examples': ['10/31/2024'],
        'extract': _extract_maxshred_date
    },
    'D & D Refuse': {
        'format': 'MM/DD/YYYY',
        'label': 'Date (columnar, wide)',
        'examples': ['07/30/2025'],
        'extract': _extract_d_and_d_refuse_date
    },
    'Big River Disposal': {
        'format': 'M/D/YYYY',
        'label': 'received on (TrashBilling)',
        'examples': ['10/1/2025'],
        'extract': _extract_big_river_disposal_date
    },
    # --- Tranche 77 ---
    'A-1 Little John': {
        'format': 'MM/DD/YYYY',
        'label': 'DATE (columnar)',
        'examples': ['11/20/2025'],
        'extract': _extract_a1_little_john_date
    },
    'Edward Arnold Scrap Processors': {
        'format': 'M/D/YYYY',
        'label': 'DATE (columnar)',
        'examples': ['2/4/2025'],
        'extract': _extract_edward_arnold_scrap_processors_date
    },
    'Parish Disposal': {
        'format': 'MM/DD/YYYY',
        'label': 'DATE (columnar)',
        'examples': ['04/15/2025'],
        'extract': _extract_parish_disposal_date
    },
    'ADS Solid Waste': {
        'format': 'MM/DD/YYYY',
        'label': 'Invoice Date: (columnar)',
        'examples': ['07/10/2025'],
        'extract': _extract_ads_solid_waste_date
    },
    'WFT Waste': {
        'format': 'M/D/YY',
        'label': 'DATE (columnar)',
        'examples': ['3/4/25'],
        'extract': _extract_wft_waste_date
    },
    "Kuerth's Disposal": {
        'format': 'MM/DD/YYYY',
        'label': 'Date (columnar)',
        'examples': ['02/09/2025'],
        'extract': _extract_kuerths_disposal_date
    },
    'Allen Disposal': {
        'format': 'M/D/YYYY',
        'label': 'received on (TrashBilling)',
        'examples': ['10/8/2025'],
        'extract': _extract_allen_disposal_date
    },
    'D&S Portable Toilets': {
        'format': 'Mon DD, YYYY',
        'label': 'Date (columnar)',
        'examples': ['Feb 20, 2025'],
        'extract': _extract_ds_portable_toilets_date
    },
    'Georgia Waste Systems': {
        'format': 'MM/DD/YYYY',
        'label': 'Invoice Date: (columnar)',
        'examples': ['02/03/2025'],
        'extract': _extract_georgia_waste_systems_date
    },
    'Westside Waste Management': {
        'format': 'MM/DD/YYYY',
        'label': 'Invoice Date: (inline)',
        'examples': ['09/30/2025'],
        'extract': _extract_westside_waste_management_date
    },
    'J&Jay Services': {
        'format': 'Mon DD, YYYY',
        'label': 'Issued Date: (columnar)',
        'examples': ['Apr 30, 2025'],
        'extract': _extract_j_and_jay_services_date
    },
    'Richland County Landfill': {
        'format': 'Mon DD, YYYY',
        'label': 'Invoice Date (columnar)',
        'examples': ['Sep 16, 2025'],
        'extract': _extract_richland_county_landfill_date
    },
    # --- Tranche 78 ---
    "Les's Sanitation": {
        'format': 'MM/DD/YY',
        'label': 'INV DATE (columnar)',
        'examples': ['12/31/25'],
        'extract': _extract_less_sanitation_date
    },
    'City of Las Cruces': {
        'format': 'M/DD/YYYY',
        'label': 'Billing Date (columnar)',
        'examples': ['4/14/2025'],
        'extract': _extract_city_of_las_cruces_date
    },
    'Southern Oregon Sanitation': {
        'format': 'MM/DD/YYYY',
        'label': 'Statement: (inline) or Bill Date',
        'examples': ['07/25/2025'],
        'extract': _extract_southern_oregon_sanitation_date
    },
    'Texas Dumpsters': {
        'format': 'MM/DD/YYYY',
        'label': 'Invoice Date (columnar)',
        'examples': ['12/18/2025'],
        'extract': _extract_texas_dumpsters_date
    },
    'City of Winfield': {
        'format': 'M/DD/YYYY',
        'label': 'BILLING DATE (columnar)',
        'examples': ['2/20/2025'],
        'extract': _extract_city_of_winfield_date
    },
    'City of Emporia': {
        'format': 'MM/DD/YYYY',
        'label': 'BILLING DATE (columnar)',
        'examples': ['03/06/2025'],
        'extract': _extract_city_of_emporia_date
    },
    'Vanderpoel Disposal': {
        'format': 'MM/DD/YYYY',
        'label': 'Payment date (columnar)',
        'examples': ['12/11/2025'],
        'extract': _extract_vanderpoel_disposal_date
    },
    'Mackenzie Disposal': {
        'format': 'MM/DD/YY',
        'label': 'INVOICE DATE (reverse columnar)',
        'examples': ['01/01/25'],
        'extract': _extract_mackenzie_disposal_date
    },
    'Community Sanitation': {
        'format': 'M/DD/YYYY',
        'label': 'DATE: (inline)',
        'examples': ['3/14/2025'],
        'extract': _extract_community_sanitation_date
    },
    'Family Trash Service': {
        'format': 'MM/DD/YYYY',
        'label': 'DATE (inline)',
        'examples': ['05/02/2025'],
        'extract': _extract_family_trash_service_date
    },
    'Cheyenne Board of Public Utilities': {
        'format': 'MM/DD/YYYY',
        'label': 'BILL DATE (columnar)',
        'examples': ['07/01/2025'],
        'extract': _extract_cheyenne_board_of_public_utilities_date
    },
    'Accurate Paper Recycling': {
        'format': 'MM/DD/YYYY',
        'label': 'DATE (columnar)',
        'examples': ['05/31/2025'],
        'extract': _extract_accurate_paper_recycling_date
    },
    # --- Tranche 79 ---
    'Wampler Services': {
        'format': 'MM/DD/YYYY',
        'label': 'Invoice Date: (columnar)',
        'examples': ['12/24/2025'],
        'extract': _extract_wampler_services_date
    },
    'Garretson Trash Service': {
        'format': 'M/DD/YYYY',
        'label': 'received on (TrashBilling)',
        'examples': ['8/11/2025'],
        'extract': _extract_garretson_trash_service_date
    },
    'Armor Environmental': {
        'format': 'MM/DD/YYYY',
        'label': 'DATE (inline)',
        'examples': ['04/28/2025'],
        'extract': _extract_armor_environmental_date
    },
    "Tim's Trash Service": {
        'format': 'YYYY-MM-DD',
        'label': 'Payment date (columnar)',
        'examples': ['2025-12-05'],
        'extract': _extract_tims_trash_service_date
    },
    'Humpty Dumpsters': {
        'format': 'MM/DD/YYYY',
        'label': 'Payment date (columnar)',
        'examples': ['06/22/2025'],
        'extract': _extract_humpty_dumpsters_date
    },
    'Recycling Center Inc': {
        'format': 'MM/DD/YYYY',
        'label': 'Date: (columnar)',
        'examples': ['12/15/2025'],
        'extract': _extract_recycling_center_inc_date
    },
    'Durflinger Disposal Service': {
        'format': 'M/DD/YYYY',
        'label': 'DATE (columnar)',
        'examples': ['3/15/2025'],
        'extract': _extract_durflinger_disposal_service_date
    },
    'Reliable Paper Recycling': {
        'format': 'MM/DD/YYYY',
        'label': 'first date in text',
        'examples': ['01/06/2025'],
        'extract': _extract_reliable_paper_recycling_date
    },
    'Darling Ingredients': {
        'format': 'MM/DD/YYYY',
        'label': 'Date (columnar)',
        'examples': ['07/12/2025'],
        'extract': _extract_darling_ingredients_date
    },
    'City of Laramie': {
        'format': 'M/DD/YYYY',
        'label': 'BILL DATE (columnar)',
        'examples': ['9/22/2025'],
        'extract': _extract_city_of_laramie_date
    },
    'City of Rolla': {
        'format': 'MM/DD/YYYY',
        'label': 'DATE (columnar)',
        'examples': ['11/06/2025'],
        'extract': _extract_city_of_rolla_date
    },
    'City of Williston': {
        'format': 'MM/DD/YYYY',
        'label': 'Billed: (inline)',
        'examples': ['08/27/2025'],
        'extract': _extract_city_of_williston_date
    },
    # --- Tranche 80 ---
    'Murray Sanitation': {
        'format': 'M/D/YYYY',
        'label': 'Invoice Date (inline)',
        'examples': ['1/1/2025'],
        'extract': _extract_murray_sanitation_date
    },
    'Nicholas Sanitation': {
        'format': 'MM/DD/YYYY',
        'label': 'Invoice Date (columnar)',
        'examples': ['07/01/2025'],
        'extract': _extract_nicholas_sanitation_date
    },
    'H & H Sanitation': {
        'format': 'MM/DD/YYYY',
        'label': 'DATE (columnar)',
        'examples': ['07/01/2025'],
        'extract': _extract_h_and_h_sanitation_date
    },
    'Key Disposal & Recycling': {
        'format': 'MM/DD/YY',
        'label': 'INV DATE (columnar)',
        'examples': ['06/30/25'],
        'extract': _extract_key_disposal_and_recycling_date
    },
    'Baker Sanitary Service': {
        'format': 'M/D/YYYY',
        'label': 'DATE (columnar wide)',
        'examples': ['1/1/2025'],
        'extract': _extract_baker_sanitary_service_date
    },
    'TBS Waste': {
        'format': 'MM/DD/YY',
        'label': 'INV DATE (columnar)',
        'examples': ['11/30/25'],
        'extract': _extract_tbs_waste_date
    },
    'Metalico Youngstown': {
        'format': 'MM/DD/YY',
        'label': 'Date: (inline no space)',
        'examples': ['12/19/25'],
        'extract': _extract_metalico_youngstown_date
    },
    'Ely Disposal Service': {
        'format': 'MM/DD/YYYY',
        'label': 'Invoice Date: (inline)',
        'examples': ['05/31/2025'],
        'extract': _extract_ely_disposal_service_date
    },
    'Town of Lusk': {
        'format': 'MM/DD/YYYY',
        'label': 'DUE DATE (columnar)',
        'examples': ['04/20/2025'],
        'extract': _extract_town_of_lusk_date
    },
    'Ed Burris Disposal': {
        'format': 'MM/DD/YY',
        'label': 'Date (columnar)',
        'examples': ['12/03/25'],
        'extract': _extract_ed_burris_disposal_date
    },
    'CDA Garbage': {
        'format': 'M/DD/YY',
        'label': 'Invoice Date (reverse columnar)',
        'examples': ['7/01/25'],
        'extract': _extract_cda_garbage_date
    },
    'Industrial Waste & Salvage': {
        'format': 'M/DD/YYYY',
        'label': 'INVOICE DATE (columnar)',
        'examples': ['1/24/2025'],
        'extract': _extract_industrial_waste_and_salvage_date
    },
    # --- Tranche 81 ---
    "Dodd's Trash Hauling": {
        'format': 'Month DD, YYYY',
        'label': 'first date found',
        'examples': ['June 1st, 2025'],
        'extract': _extract_dodds_trash_hauling_date
    },
    'JDog Junk Removal': {
        'format': 'Weekday Mon DD, YYYY',
        'label': 'Date (columnar)',
        'examples': ['Tue Aug 26, 2025'],
        'extract': _extract_jdog_junk_removal_date
    },
    'All Star Roll-Off': {
        'format': 'Mon DD, YYYY',
        'label': 'Invoice Date (columnar)',
        'examples': ['Mar 10, 2025'],
        'extract': _extract_all_star_roll_off_date
    },
    'Pratt Sanitation': {
        'format': 'M/D/YYYY',
        'label': 'received on (TrashBilling)',
        'examples': ['1/9/2026'],
        'extract': _extract_pratt_sanitation_date
    },
    'Advanced Document Solutions': {
        'format': 'MM/DD/YYYY',
        'label': 'Invoice Print Date: (columnar)',
        'examples': ['07/28/2025'],
        'extract': _extract_advanced_document_solutions_date
    },
    'City of Hobbs': {
        'format': 'M/DD/YYYY',
        'label': 'BILLING DATE: (columnar)',
        'examples': ['6/24/2025'],
        'extract': _extract_city_of_hobbs_date
    },
    "Jon's Refuse Solutions": {
        'format': 'MM/DD/YYYY',
        'label': 'DATE (columnar)',
        'examples': ['12/31/2025'],
        'extract': _extract_jons_refuse_solutions_date
    },
    'Bainbridge Disposal': {
        'format': 'MM/DD/YYYY',
        'label': 'Transaction Date: (columnar)',
        'examples': ['05/16/2025'],
        'extract': _extract_bainbridge_disposal_date
    },
    'Marcotte Disposal': {
        'format': 'Weekday Mon DD, YYYY',
        'label': 'first Weekday Mon DD date',
        'examples': ['Fri Feb 28, 2025'],
        'extract': _extract_marcotte_disposal_date
    },
    'City of Devils Lake': {
        'format': 'MM/DD/YYYY',
        'label': 'Billing Period End (columnar)',
        'examples': ['04/30/2025'],
        'extract': _extract_city_of_devils_lake_date
    },
    'Hillsboro Garbage Disposal': {
        'format': 'MM/DD/YYYY',
        'label': 'Statement Date (columnar)',
        'examples': ['12/31/2025'],
        'extract': _extract_hillsboro_garbage_disposal_date
    },
    'R&R Recycling Inc': {
        'format': 'M/DD/YYYY',
        'label': 'Date (columnar)',
        'examples': ['4/30/2025'],
        'extract': _extract_r_and_r_recycling_inc_date
    },
    # --- Tranche 82 ---
    'Wemiga Waste': {
        'format': 'M/DD/YYYY',
        'label': 'Date (columnar)',
        'examples': ['9/30/2025'],
        'extract': _extract_wemiga_waste_date
    },
    'Sweetland': {
        'format': 'MM/DD/YYYY',
        'label': 'Date (columnar)',
        'examples': ['08/27/2025'],
        'extract': _extract_sweetland_date
    },
    'City of Socorro': {
        'format': 'M/DD/YYYY',
        'label': 'Bill Date (columnar wide)',
        'examples': ['6/23/2025'],
        'extract': _extract_city_of_socorro_date
    },
    'Moon Companies': {
        'format': 'MM/DD/YYYY',
        'label': 'DATE (inline)',
        'examples': ['08/11/2025'],
        'extract': _extract_moon_companies_date
    },
    'Iron Mountain': {
        'format': 'Month DD, YYYY',
        'label': 'Invoice Date or first date',
        'examples': ['August 1, 2025'],
        'extract': _extract_iron_mountain_date
    },
    'Kaibab Band': {
        'format': 'MM/DD/YYYY',
        'label': 'PERIOD ENDING: (inline)',
        'examples': ['09/30/2025'],
        'extract': _extract_kaibab_band_date
    },
    'Town of Wickenburg': {
        'format': 'M/DD/YYYY',
        'label': 'Notice Date: (inline)',
        'examples': ['7/23/2025'],
        'extract': _extract_town_of_wickenburg_date
    },
    'Fisk Waste Removal': {
        'format': 'MM/DD/YY',
        'label': 'BILL DATE (columnar)',
        'examples': ['12/01/25'],
        'extract': _extract_fisk_waste_removal_date
    },
    'Town of Dutch John': {
        'format': 'M/D/YYYY',
        'label': 'Date (columnar)',
        'examples': ['8/1/2025'],
        'extract': _extract_town_of_dutch_john_date
    },
    'Waste Recycling Inc': {
        'format': 'M/D/YYYY',
        'label': 'Date (columnar)',
        'examples': ['7/1/2025'],
        'extract': _extract_waste_recycling_inc_date
    },
    'Ultimate Specialties': {
        'format': 'MM/DD/YYYY',
        'label': 'Date (columnar)',
        'examples': ['11/15/2025'],
        'extract': _extract_ultimate_specialties_date
    },
    'BCDA The Trash Company': {
        'format': 'Weekday Mon DD, YYYY',
        'label': 'TrashBilling date',
        'examples': ['Sun Jul 20, 2025'],
        'extract': _extract_bcda_the_trash_company_date
    },
    # --- Tranche 83 ---
    'MCS Midwest': {
        'format': 'MM/DD/YYYY',
        'label': 'Date (columnar)',
        'examples': ['12/30/2025'],
        'extract': _extract_mcs_midwest_date
    },
    'Pleasanton Garbage': {
        'format': 'M/DD/YYYY',
        'label': 'INVOICE DATE (columnar)',
        'examples': ['7/31/2025'],
        'extract': _extract_pleasanton_garbage_date
    },
    'McAllen Public Utility': {
        'format': 'M/DD/YYYY',
        'label': 'Billing Date: (inline)',
        'examples': ['6/13/2025'],
        'extract': _extract_mcallen_public_utility_date
    },
    'City of Lamar': {
        'format': 'MM/DD/YY',
        'label': 'Bill Date (columnar)',
        'examples': ['09/29/25'],
        'extract': _extract_city_of_lamar_date
    },
    'American Hauling Services': {
        'format': 'Month DD, YYYY',
        'label': 'Invoice Date: (inline)',
        'examples': ['July 20, 2025'],
        'extract': _extract_american_hauling_services_date
    },
    'Andy Gump': {
        'format': 'MM/DD/YYYY',
        'label': 'first date found',
        'examples': ['12/01/2025'],
        'extract': _extract_andy_gump_date
    },
    'CTL Washington': {
        'format': 'MM/DD/YYYY',
        'label': 'Invoice Date: (inline)',
        'examples': ['12/31/2025'],
        'extract': _extract_ctl_washington_date
    },
    'Town of Limon': {
        'format': 'MM/DD/YY',
        'label': 'DUE DATE: (columnar)',
        'examples': ['04/15/25'],
        'extract': _extract_town_of_limon_date
    },
    'Mosdell Sanitation': {
        'format': 'Weekday Mon DD, YYYY',
        'label': 'TrashBilling date',
        'examples': ['Wed Apr 30, 2025'],
        'extract': _extract_mosdell_sanitation_date
    },
    'Food To Power': {
        'format': 'Month DD, YYYY',
        'label': 'Date of issue (inline)',
        'examples': ['August 26, 2025'],
        'extract': _extract_food_to_power_date
    },
    'Equipment Depot Northeast': {
        'format': 'M/D/YYYY',
        'label': 'Billing Date (columnar)',
        'examples': ['5/1/2025'],
        'extract': _extract_equipment_depot_northeast_date
    },
    'City of Columbia MO': {
        'format': 'M/DD/YYYY',
        'label': 'INVOICE DATE (columnar)',
        'examples': ['4/30/2025'],
        'extract': _extract_city_of_columbia_mo_date
    },
    # --- Tranche 84 ---
    'Southern Disposal AR': {
        'format': 'M/D/YYYY',
        'label': 'Date (columnar)',
        'examples': ['12/1/2025'],
        'extract': _extract_southern_disposal_ar_date
    },
    'Always Green Recycling': {
        'format': 'M/D/YYYY',
        'label': 'Date (columnar)',
        'examples': ['11/1/2025'],
        'extract': _extract_always_green_recycling_date
    },
    'Save That Stuff': {
        'format': 'M/DD/YY',
        'label': 'Invoice Date (columnar)',
        'examples': ['1/31/25'],
        'extract': _extract_save_that_stuff_date
    },
    'Russell County Sanitation': {
        'format': 'MM/DD/YYYY',
        'label': 'Billing Date: (columnar wide)',
        'examples': ['02/24/2025'],
        'extract': _extract_russell_county_sanitation_date
    },
    'City of Lewiston': {
        'format': 'MM/DD/YYYY',
        'label': 'Bill Date (columnar)',
        'examples': ['06/24/2025'],
        'extract': _extract_city_of_lewiston_date
    },
    'Green River Waste': {
        'format': 'MM/DD/YY',
        'label': 'INV DATE (columnar)',
        'examples': ['11/01/25'],
        'extract': _extract_green_river_waste_date
    },
    'Roll-Off Chick': {
        'format': 'MM/D/YYYY',
        'label': 'Invoice Date: (inline)',
        'examples': ['09/9/2025'],
        'extract': _extract_roll_off_chick_date
    },
    'Pinto Service': {
        'format': 'MM/DD/YY',
        'label': 'Invoice Date (columnar)',
        'examples': ['12/31/24'],
        'extract': _extract_pinto_service_date
    },
    'Reed Maintenance': {
        'format': 'MM/DD/YYYY',
        'label': 'Invoice Date: (inline)',
        'examples': ['04/24/2025'],
        'extract': _extract_reed_maintenance_date
    },
    'Tovar Equipment': {
        'format': 'Mon DD, YYYY',
        'label': 'Invoice date (columnar)',
        'examples': ['Aug 6, 2025'],
        'extract': _extract_tovar_equipment_date
    },
    'Torrez Sanitation': {
        'format': 'Weekday Mon DD, YYYY',
        'label': 'TrashBilling date',
        'examples': ['Tue Dec 2, 2025'],
        'extract': _extract_torrez_sanitation_date
    },
    "Sid's Garbage": {
        'format': 'MM/DD/YYYY',
        'label': 'Invoice date: (inline)',
        'examples': ['01/01/2026'],
        'extract': _extract_sids_garbage_date
    },
    # --- Tranche 85 ---
    'Aztec Waste': {
        'format': 'MM/DD/YY',
        'label': 'INV DATE (columnar)',
        'examples': ['07/25/25'],
        'extract': _extract_aztec_waste_date
    },
    'Pyles Demolition Recycling': {
        'format': 'M/D/YYYY',
        'label': 'Date (columnar)',
        'examples': ['10/2/2025'],
        'extract': _extract_pyles_demolition_recycling_date
    },
    'Serious Sanitation': {
        'format': 'MM/DD/YYYY',
        'label': 'DATE (columnar)',
        'examples': ['04/02/2025'],
        'extract': _extract_serious_sanitation_date
    },
    'Busy Bee Disposal': {
        'format': 'Weekday Mon D, YYYY',
        'label': 'Date: (TrashBilling)',
        'examples': ['Thu Jul 3, 2025'],
        'extract': _extract_busy_bee_disposal_date
    },
    "Gil's Sanitation": {
        'format': 'M/DD/YYYY',
        'label': 'Invoice Date (columnar)',
        'examples': ['5/31/2025'],
        'extract': _extract_gils_sanitation_date
    },
    'Buckingham Companies': {
        'format': 'MM/DD/YYYY',
        'label': 'Invoice Date: (inline)',
        'examples': ['03/01/2025'],
        'extract': _extract_buckingham_companies_date
    },
    'City of Baxley': {
        'format': 'M/DD/YYYY',
        'label': 'first date found',
        'examples': ['3/16/2025'],
        'extract': _extract_city_of_baxley_date
    },
    'Anchorage Solid Waste': {
        'format': 'MM/DD/YYYY',
        'label': 'BILL DATE: (inline)',
        'examples': ['03/31/2025'],
        'extract': _extract_anchorage_solid_waste_date
    },
    'HBS Denver': {
        'format': 'MM/DD/YYYY',
        'label': 'INVOICE DATE (columnar)',
        'examples': ['05/31/2025'],
        'extract': _extract_hbs_denver_date
    },
    'Toro Waste': {
        'format': 'MM/DD/YYYY',
        'label': 'near INVOICE header',
        'examples': ['06/04/2025'],
        'extract': _extract_toro_waste_date
    },
    'North Port Solid Waste': {
        'format': 'M/DD/YY',
        'label': 'BILL DATE (columnar)',
        'examples': ['9/05/25'],
        'extract': _extract_north_port_solid_waste_date
    },
    'North Iredell Sanitation': {
        'format': 'Month DD, YYYY',
        'label': 'Date of issue (inline)',
        'examples': ['September 26, 2025'],
        'extract': _extract_north_iredell_sanitation_date
    },
    # --- Tranche 86 ---
    'City of Craig': {
        'format': 'MM/DD/YYYY',
        'label': 'Billing Period End (columnar)',
        'examples': ['02/28/2025'],
        'extract': _extract_city_of_craig_date
    },
    'Prolex Compacting': {
        'format': 'MM/DD/YYYY',
        'label': 'DATE (inline)',
        'examples': ['12/01/2025'],
        'extract': _extract_prolex_compacting_date
    },
    'Graybill Equipment & Repair': {
        'format': 'MM/DD/YYYY',
        'label': 'Date (columnar)',
        'examples': ['11/10/2025'],
        'extract': _extract_graybill_equipment_date
    },
    'Aspen Leasing': {
        'format': 'MM/DD/YYYY',
        'label': 'Invoice Date (inline)',
        'examples': ['03/17/2025'],
        'extract': _extract_aspen_leasing_date
    },
    'Mid-Ohio Sanitation & Recycling': {
        'format': 'Weekday Mon D, YYYY',
        'label': 'TrashBilling date',
        'examples': ['Mon Nov 3, 2025'],
        'extract': _extract_mid_ohio_sanitation_date
    },
    "Jim Dedman's Sanitation": {
        'format': 'Weekday Mon DD, YYYY',
        'label': 'Date: (TrashBilling)',
        'examples': ['Wed Jun 25, 2025'],
        'extract': _extract_jim_dedmans_sanitation_date
    },
    'Delta Disposal': {
        'format': 'Weekday Mon D, YYYY',
        'label': 'TrashBilling date',
        'examples': ['Mon Dec 1, 2025'],
        'extract': _extract_delta_disposal_date
    },
    'Redwood Landfill': {
        'format': 'Mon DD, YYYY',
        'label': 'Invoice Date (columnar)',
        'examples': ['Nov 16, 2025'],
        'extract': _extract_redwood_landfill_date
    },
    'City of Scottsbluff': {
        'format': 'M/DD/YYYY',
        'label': 'Billing Date (columnar)',
        'examples': ['1/24/2025'],
        'extract': _extract_city_of_scottsbluff_date
    },
    'Hughes Waste Haulers': {
        'format': 'M/DD/YYYY',
        'label': 'Date (columnar)',
        'examples': ['9/30/2025'],
        'extract': _extract_hughes_waste_haulers_date
    },
    'Mountain High Disposal': {
        'format': 'MM/DD/YYYY',
        'label': 'Date (columnar)',
        'examples': ['12/15/2025'],
        'extract': _extract_mountain_high_disposal_date
    },
    'DuMontelle Waste': {
        'format': 'MM/DD/YYYY',
        'label': 'Invoice date: (inline)',
        'examples': ['07/23/2025'],
        'extract': _extract_dumontelle_waste_date
    },
    # --- Tranche 87 ---
    'Mogford Metals': {
        'format': 'MM/DD/YYYY',
        'label': 'Date: (columnar)',
        'examples': ['05/10/2025'],
        'extract': _extract_mogford_metals_date
    },
    'Anaconda Disposal': {
        'format': 'Weekday Mon DD, YYYY',
        'label': 'TrashBilling date',
        'examples': ['Sun Nov 30, 2025'],
        'extract': _extract_anaconda_disposal_date
    },
    'Post Environmental Services': {
        'format': 'MM/DD/YYYY',
        'label': 'Invoice date: (inline)',
        'examples': ['01/01/2025'],
        'extract': _extract_post_environmental_services_date
    },
    'Virgin Valley Disposal': {
        'format': 'M/DD/YYYY',
        'label': 'INVOICE DATE: (inline)',
        'examples': ['9/02/2025'],
        'extract': _extract_virgin_valley_disposal_date
    },
    'WM Collection': {
        'format': 'MM/DD/YYYY',
        'label': 'Invoice Date: (columnar)',
        'examples': ['11/01/2025'],
        'extract': _extract_wm_collection_date
    },
    'American Metal & Paper': {
        'format': 'MM/DD/YYYY',
        'label': 'Invoice Date: (inline)',
        'examples': ['11/04/2025'],
        'extract': _extract_american_metal_and_paper_date
    },
    'United Waste Haulers': {
        'format': 'MM/DD/YYYY',
        'label': 'INVOICE DATE (reverse columnar)',
        'examples': ['01/01/2025'],
        'extract': _extract_united_waste_haulers_date
    },
    'Walker Garbage and Recycling': {
        'format': 'MM/DD/YY',
        'label': 'Bill Date (inline)',
        'examples': ['08/31/25'],
        'extract': _extract_walker_garbage_and_recycling_date
    },
    'TNR Hauling': {
        'format': 'MM/DD/YYYY',
        'label': 'Invoice date: (inline)',
        'examples': ['12/18/2025'],
        'extract': _extract_tnr_hauling_date
    },
    'City of Yuma': {
        'format': 'MM/DD/YYYY',
        'label': 'BILLING DATE: (columnar)',
        'examples': ['10/31/2025'],
        'extract': _extract_city_of_yuma_date
    },
    'Mills Bros': {
        'format': 'MM/DD/YY',
        'label': 'STATEMENT DATE: (columnar)',
        'examples': ['05/01/25'],
        'extract': _extract_mills_bros_date
    },
    'Tomorrow RDS': {
        'format': 'MM/DD/YYYY',
        'label': 'DATE (reverse columnar)',
        'examples': ['09/30/2025'],
        'extract': _extract_tomorrow_rds_date
    },
    # --- Tranche 88 ---
    'EWE Equipment': {
        'format': 'MM/DD/YY',
        'label': 'Invoice Date (columnar)',
        'examples': ['2/27/25'],
        'extract': _extract_ewe_equipment_date
    },
    'Flash Trash': {
        'format': 'MM/DD/YYYY',
        'label': 'DATE (columnar)',
        'examples': ['06/01/2025'],
        'extract': _extract_flash_trash_date
    },
    'City of Barstow': {
        'format': 'MM/DD/YYYY',
        'label': 'BILL DATE (columnar)',
        'examples': ['07/07/2025'],
        'extract': _extract_city_of_barstow_date
    },
    'Civicorps Recycling': {
        'format': 'MM/DD/YYYY',
        'label': 'Date of Issue (columnar)',
        'examples': ['10/01/2025'],
        'extract': _extract_civicorps_recycling_date
    },
    'P&S Trucking': {
        'format': 'Mon DD, YYYY',
        'label': 'Issue date (columnar)',
        'examples': ['Dec 1, 2025'],
        'extract': _extract_ps_trucking_date
    },
    'White Mountain Apache': {
        'format': 'M/D/YYYY',
        'label': 'Date: (inline)',
        'examples': ['9/2/2025'],
        'extract': _extract_white_mountain_apache_date
    },
    'Evergreen Paper Recycling': {
        'format': 'MM/DD/YYYY',
        'label': 'DATE (columnar)',
        'examples': ['01/31/2025'],
        'extract': _extract_evergreen_paper_recycling_date
    },
    'Rahn Sanitary': {
        'format': 'MM/DD/YYYY',
        'label': 'Bill Date: (reverse columnar)',
        'examples': ['9/30/2025'],
        'extract': _extract_rahn_sanitary_date
    },
    'Maguire Equipment': {
        'format': 'M/D/YYYY',
        'label': 'Date (columnar)',
        'examples': ['7/1/2025'],
        'extract': _extract_maguire_equipment_date
    },
    'Cook Sanitation': {
        'format': 'M/DD/YY',
        'label': 'Bill Date: (inline)',
        'examples': ['7/30/25'],
        'extract': _extract_cook_sanitation_date
    },
    'Eagle Equipment Corporation': {
        'format': 'MM/DD/YY',
        'label': 'INVOICE DATE (columnar)',
        'examples': ['02/28/25'],
        'extract': _extract_eagle_equipment_corporation_date
    },
    'Big Bear Disposal': {
        'format': 'M/D/YYYY',
        'label': 'INVOICE DATE (columnar)',
        'examples': ['5/1/2025'],
        'extract': _extract_big_bear_disposal_date
    },
    # --- Tranche 89 ---
    'City of Lake Mary': {
        'format': 'MM/DD/YY',
        'label': 'Bill Date (columnar)',
        'examples': ['10/25/25'],
        'extract': _extract_city_of_lake_mary_date
    },
    'Generated Materials Recovery': {
        'format': 'MM/DD/YY',
        'label': 'Invoice Date (reverse columnar)',
        'examples': ['07/31/25'],
        'extract': _extract_generated_materials_recovery_date
    },
    'Styro Recycle': {
        'format': 'MM/DD/YYYY',
        'label': 'Date (columnar)',
        'examples': ['12/31/2025'],
        'extract': _extract_styro_recycle_date
    },
    'Buldo Container & Disposal': {
        'format': 'DD-Mon-YYYY',
        'label': 'DATE (reverse columnar)',
        'examples': ['05-Nov-2025'],
        'extract': _extract_buldo_container_disposal_date
    },
    'Desert Green Disposal': {
        'format': 'M/D/YYYY',
        'label': 'Date (columnar)',
        'examples': ['4/1/2025'],
        'extract': _extract_desert_green_disposal_date
    },
    'Capital Area Refuse': {
        'format': 'M/D/YYYY',
        'label': 'received on (TrashBilling)',
        'examples': ['10/17/2025'],
        'extract': _extract_capital_area_refuse_date
    },
    'City of Lebanon': {
        'format': 'Month DD, YYYY',
        'label': 'DATE: (inline)',
        'examples': ['DECEMBER 31, 2024'],
        'extract': _extract_city_of_lebanon_date
    },
    'Liberty Ashes': {
        'format': 'Weekday Mon DD, YYYY',
        'label': 'TrashBilling date',
        'examples': ['Thu May 1, 2025'],
        'extract': _extract_liberty_ashes_date
    },
    'Kluesner Sanitation': {
        'format': 'MM/DD/YYYY',
        'label': 'Invoice Date (columnar)',
        'examples': ['11/03/2025'],
        'extract': _extract_kluesner_sanitation_date
    },
    'G & H Garbage': {
        'format': 'MM/DD/YY',
        'label': 'INV DATE (columnar)',
        'examples': ['03/31/25'],
        'extract': _extract_g_h_garbage_date
    },
    'Seagraves Plumbing': {
        'format': 'Mon D, YYYY',
        'label': 'Invoice Date: (inline)',
        'examples': ['Dec 8, 2025'],
        'extract': _extract_seagraves_plumbing_date
    },
    'Lakeside Recycling': {
        'format': 'Weekday Mon DD, YYYY',
        'label': 'TrashBilling date',
        'examples': ['Sun Nov 30, 2025'],
        'extract': _extract_lakeside_recycling_date
    },
    # --- Tranche 90 ---
    'Columbia County Solid Waste': {
        'format': 'MM/DD/YYYY',
        'label': 'INVOICE DATE (columnar)',
        'examples': ['7/31/2025'],
        'extract': _extract_columbia_county_solid_waste_date
    },
    'Thomas Trash': {
        'format': 'MM/DD/YY',
        'label': 'INV DATE (columnar)',
        'examples': ['08/31/25'],
        'extract': _extract_thomas_trash_date
    },
    'Town of Babylon': {
        'format': 'MM/DD/YYYY',
        'label': 'Invoice Date (columnar)',
        'examples': ['06/30/2025'],
        'extract': _extract_town_of_babylon_date
    },
    'Harley Hollan': {
        'format': 'MM/DD/YYYY',
        'label': 'Invoice Date: (inline)',
        'examples': ['09/30/2025'],
        'extract': _extract_harley_hollan_date
    },
    'Fiber Services': {
        'format': 'MM/DD/YYYY',
        'label': 'statement period start',
        'examples': ['02/01/2025'],
        'extract': _extract_fiber_services_date
    },
    'City of Redwood': {
        'format': 'MM/DD/YY',
        'label': 'Billed: (columnar)',
        'examples': ['11/28/24'],
        'extract': _extract_city_of_redwood_date
    },
    'City of Dickson': {
        'format': 'MM/DD/YYYY',
        'label': 'DATE (inline)',
        'examples': ['02/01/2025'],
        'extract': _extract_city_of_dickson_date
    },
    "Dan's R Us Sanitation": {
        'format': 'MM/DD/YYYY',
        'label': 'Invoice Date: (inline)',
        'examples': ['01/07/2026'],
        'extract': _extract_dans_r_us_sanitation_date
    },
    'Roller Industrial': {
        'format': 'M/DD/YYYY',
        'label': 'DATE (columnar)',
        'examples': ['4/26/2025'],
        'extract': _extract_roller_industrial_date
    },
    'RES Waste': {
        'format': 'MM/DD/YYYY',
        'label': 'Date (columnar)',
        'examples': ['01/01/2026'],
        'extract': _extract_res_waste_date
    },
    'City of Hidalgo': {
        'format': 'M/DD/YYYY',
        'label': 'Billing Date (columnar)',
        'examples': ['7/14/2025'],
        'extract': _extract_city_of_hidalgo_date
    },
    'City of Huron': {
        'format': 'MM/DD/YY',
        'label': 'BILLING DATE (columnar)',
        'examples': ['05/31/25'],
        'extract': _extract_city_of_huron_date
    },
    # --- Tranche 91 ---
    'Horn Sanitation': {
        'format': 'Mon DD, YYYY',
        'label': 'Issued (columnar)',
        'examples': ['Dec 29, 2025'],
        'extract': _extract_horn_sanitation_date
    },
    'Sutter Disposal': {
        'format': 'Weekday Mon D, YYYY',
        'label': 'TrashBilling date',
        'examples': ['Tue Sep 2, 2025'],
        'extract': _extract_sutter_disposal_date
    },
    'Self Recycling': {
        'format': 'M/DD/YYYY',
        'label': 'Date (columnar)',
        'examples': ['1/31/2025'],
        'extract': _extract_self_recycling_date
    },
    'Nisly Brothers': {
        'format': 'Mon DD, YYYY',
        'label': 'DATE (columnar)',
        'examples': ['Feb 19, 2025'],
        'extract': _extract_nisly_brothers_date
    },
    'A&L Compaction': {
        'format': 'M/DD/YYYY',
        'label': 'Date (columnar)',
        'examples': ['7/15/2025'],
        'extract': _extract_al_compaction_date
    },
    "Mac's Wood Products": {
        'format': 'MM/DD/YYYY',
        'label': 'after INVOICE',
        'examples': ['08/25/2025'],
        'extract': _extract_macs_wood_products_date
    },
    'Eagle Equipment Service 1': {
        'format': 'MM/DD/YYYY',
        'label': 'DATE (inline)',
        'examples': ['11/24/2025'],
        'extract': _extract_eagle_equipment_service_1_date
    },
    'Boulder City Disposal': {
        'format': 'MM/DD/YY',
        'label': 'Statement Date: (inline)',
        'examples': ['12/31/25'],
        'extract': _extract_boulder_city_disposal_date
    },
    'City of Loganville': {
        'format': 'MM/DD/YYYY',
        'label': 'Bill Date (columnar)',
        'examples': ['10/21/2025'],
        'extract': _extract_city_of_loganville_date
    },
    'Pak-Rite Rentals': {
        'format': 'M/D/YYYY',
        'label': 'Date (columnar)',
        'examples': ['2/1/2025'],
        'extract': _extract_pak_rite_rentals_date
    },
    'Town of Greeneville': {
        'format': 'MM/DD/YYYY',
        'label': 'Service Period start',
        'examples': ['06/01/2025'],
        'extract': _extract_town_of_greeneville_date
    },
    "David's Trash Service": {
        'format': 'Weekday Mon DD, YYYY',
        'label': 'TrashBilling date',
        'examples': ['Thu Oct 16, 2025'],
        'extract': _extract_davids_trash_service_date
    },
    # --- Tranche 92 ---
    'City of Enumclaw': {
        'format': 'MM/DD/YY',
        'label': 'DATE BILLED (columnar)',
        'examples': ['04/30/25'],
        'extract': _extract_city_of_enumclaw_date
    },
    'Johnson City Utility': {
        'format': 'MM-DD-YY',
        'label': 'SERVICE FROM (columnar)',
        'examples': ['06-30-25'],
        'extract': _extract_johnson_city_utility_date
    },
    'First Capitol Salvage': {
        'format': 'MM/DD/YYYY',
        'label': 'INVOICE DATE (columnar)',
        'examples': ['08/20/2025'],
        'extract': _extract_first_capitol_salvage_date
    },
    'Excess Disposal': {
        'format': 'M/DD/YYYY',
        'label': 'Billing Date (columnar)',
        'examples': ['8/31/2025'],
        'extract': _extract_excess_disposal_date
    },
    'Dirty Boyz Sanitation': {
        'format': 'MM/DD/YYYY',
        'label': 'Service Date (inline)',
        'examples': ['11/30/2025'],
        'extract': _extract_dirty_boyz_sanitation_date
    },
    "Cliff's Commercial Trash": {
        'format': 'M/DD/YYYY',
        'label': 'Date (columnar)',
        'examples': ['4/30/2025'],
        'extract': _extract_cliffs_commercial_trash_date
    },
    'J&J Sanitation': {
        'format': 'MM/DD/YY',
        'label': 'STATEMENT DATE (columnar)',
        'examples': ['12/01/25'],
        'extract': _extract_jj_sanitation_date
    },
    'SRG Spartanburg': {
        'format': 'MM/DD/YYYY',
        'label': 'Inv Date: (inline)',
        'examples': ['11/30/2025'],
        'extract': _extract_srg_spartanburg_date
    },
    'Kept Companies': {
        'format': 'Month DD, YYYY',
        'label': 'Date: (columnar)',
        'examples': ['September 30, 2025'],
        'extract': _extract_kept_companies_date
    },
    'C & H Disposal': {
        'format': 'M/D/YYYY',
        'label': 'DATE (columnar)',
        'examples': ['2/3/2025'],
        'extract': _extract_c_h_disposal_date
    },
    'LCI Services': {
        'format': 'MM/DD/YYYY',
        'label': 'Invoice Date: (inline)',
        'examples': ['10/07/2025'],
        'extract': _extract_lci_services_date
    },
    'Hudgins Disposal': {
        'format': 'M/D/YYYY',
        'label': 'received on (TrashBilling)',
        'examples': ['12/1/2025'],
        'extract': _extract_hudgins_disposal_date
    },
    # --- Tranche 93 ---
    'Hopper Disposal': {
        'format': 'MM/DD/YYYY',
        'label': 'Date (columnar)',
        'examples': ['12/31/2025'],
        'extract': _extract_hopper_disposal_date
    },
    'Desert Valley Disposal': {
        'format': 'MM/DD/YY',
        'label': 'first date',
        'examples': ['10/09/25'],
        'extract': _extract_desert_valley_disposal_date
    },
    'Solid Waste Disposal Authority': {
        'format': 'MM/DD/YYYY',
        'label': 'BILLING DATE: (columnar)',
        'examples': ['06/01/2025'],
        'extract': _extract_solid_waste_disposal_authority_date
    },
    'My Green Michigan': {
        'format': 'MM/DD/YYYY',
        'label': 'Invoice date: (inline)',
        'examples': ['12/31/2025'],
        'extract': _extract_my_green_michigan_date
    },
    'Mauldin Trash': {
        'format': 'M/D/YYYY',
        'label': 'DATE (columnar)',
        'examples': ['1/2/2026'],
        'extract': _extract_mauldin_trash_date
    },
    'Redfish Recycling': {
        'format': 'MM/DD/YYYY',
        'label': 'Payment date (columnar)',
        'examples': ['12/15/2025'],
        'extract': _extract_redfish_recycling_date
    },
    'Carrier Container': {
        'format': 'MM/DD/YYYY',
        'label': 'DATE (columnar)',
        'examples': ['06/01/2025'],
        'extract': _extract_carrier_container_date
    },
    'D&S Waste': {
        'format': 'MM/DD/YY',
        'label': 'INV DATE (columnar)',
        'examples': ['01/15/25'],
        'extract': _extract_ds_waste_date
    },
    'LJP Waste': {
        'format': 'MM/DD/YYYY',
        'label': 'Date (columnar)',
        'examples': ['10/31/2025'],
        'extract': _extract_ljp_waste_date
    },
    'HESCO Hydraulic': {
        'format': 'MM/DD/YYYY',
        'label': 'first date',
        'examples': ['03/19/2025'],
        'extract': _extract_hesco_hydraulic_date
    },
    'City of Henagar': {
        'format': 'MM/DD/YYYY',
        'label': 'Date (columnar)',
        'examples': ['11/01/2025'],
        'extract': _extract_city_of_henagar_date
    },
    'Waste Partners': {
        'format': 'MM/DD/YY',
        'label': 'INV DATE (columnar)',
        'examples': ['05/01/25'],
        'extract': _extract_waste_partners_date
    },
    # --- Tranche 94 ---
    'Tate Services': {
        'format': 'M/D/YYYY',
        'label': 'INVOICE DATE (columnar)',
        'examples': ['11/3/2025'],
        'extract': _extract_tate_services_date
    },
    'Local Waste of Upstate': {
        'format': 'Mon DD, YYYY',
        'label': 'first Mon DD, YYYY date',
        'examples': ['Sep 15, 2025'],
        'extract': _extract_local_waste_of_upstate_date
    },
    'Fritz Enterprises': {
        'format': 'MM/DD/YYYY',
        'label': 'DATE (reverse columnar)',
        'examples': ['02/28/2025'],
        'extract': _extract_fritz_enterprises_date
    },
    'Island Recycling': {
        'format': 'M/D/YYYY',
        'label': 'DATE (wide columnar)',
        'examples': ['6/30/2025'],
        'extract': _extract_island_recycling_date
    },
    'Sphuler Disposal': {
        'format': 'MM/DD/YYYY',
        'label': 'DATE (inline)',
        'examples': ['11/20/2025'],
        'extract': _extract_sphuler_disposal_date
    },
    'Brookings Dumpster Service': {
        'format': 'M/D/YYYY',
        'label': 'Date (columnar)',
        'examples': ['7/1/2025'],
        'extract': _extract_brookings_dumpster_service_date
    },
    'Harper Sanitation': {
        'format': 'Weekday Mon DD, YYYY',
        'label': 'TrashBilling date',
        'examples': ['Wed Jul 23, 2025'],
        'extract': _extract_harper_sanitation_date
    },
}
