"""
Date Extraction NG Fixes - February 2026
Vendor-specific date extractors for NG Report invoice formats.
Overrides/supplements extractors in date_extraction_additions.py.

These fix extraction failures where the NG report invoices use different
formats than the broader invoice volume dataset.
"""
import re
from typing import Optional

MONTH_MAP = {
    'january': 1, 'february': 2, 'march': 3, 'april': 4,
    'may': 5, 'june': 6, 'july': 7, 'august': 8,
    'september': 9, 'october': 10, 'november': 11, 'december': 12,
    'jan': 1, 'feb': 2, 'mar': 3, 'apr': 4,
    'jun': 6, 'jul': 7, 'aug': 8, 'sep': 9,
    'oct': 10, 'nov': 11, 'dec': 12,
}


def _fmt(month: int, day: int, year: int) -> Optional[str]:
    """Format and validate a date."""
    if year < 100:
        year = 2000 + year if year < 50 else 1900 + year
    if 1 <= month <= 12 and 1 <= day <= 31 and 2015 <= year <= 2035:
        return f"{year}-{month:02d}-{day:02d}"
    return None


def _try_mdy(text: str, pattern: str, flags=0) -> Optional[str]:
    """Try a regex pattern and parse as M/D/Y."""
    m = re.search(pattern, text, flags)
    if m:
        return _fmt(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    return None


def _extract_edco_ng(text: str) -> Optional[str]:
    """EDCO: account_code MM/DD/YY on address/detail line.
    Format 1: 22-NC 513475 11/30/24
    Format 2: 22-NC 513473 | 09/30/25. (with pipe separator)
    Format 3: §9-AN 354951. 08/01/25. (garbled account prefix)
    Fallback: Month DD, YYYY or first valid date
    """
    # Account code + date (with optional pipe and period)
    m = re.search(r'\d{2}-\w{2}\s+\d{6}[\s|.]+(\d{1,2})/(\d{1,2})/(\d{2,4})', text)
    if m:
        return _fmt(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    # Garbled account prefix + date: XX-AN NNNNNN. MM/DD/YY
    m = re.search(r'\w{2}-\w{2}\s+\d{6}[\s|.]+(\d{1,2})/(\d{1,2})/(\d{2,4})', text)
    if m:
        result = _fmt(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        if result:
            return result
    # BILLING DATE columnar
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if 'BILLING DATE' in line.upper():
            for j in range(i + 1, min(i + 5, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _fmt(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    # Month name fallback: July 1, 2025
    m = re.search(r'\b(January|February|March|April|May|June|July|August|September|October|November|December)\s+(\d{1,2}),?\s*(\d{4})', text, re.I)
    if m:
        month_num = MONTH_MAP.get(m.group(1).lower()[:3])
        if month_num:
            return _fmt(month_num, int(m.group(2)), int(m.group(3)))
    # First valid M/DD/YY date in text
    for m in re.finditer(r'(\d{1,2})/(\d{1,2})/(\d{2,4})', text):
        result = _fmt(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        if result:
            return result
    return None


def _extract_kmg_ng(text: str) -> Optional[str]:
    """KMG: Payment stub: account date invoice# amount.
    Format: 006238 6/15/2025 0000483416 $814.86
    Also: INVOICE DATE columnar (original pattern)
    """
    # Payment stub: 6-digit account, date, 10-digit invoice, $amount
    m = re.search(r'\d{6}\s+(\d{1,2})/(\d{1,2})/(\d{4})\s+\d{10}\s+\$', text)
    if m:
        return _fmt(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    # INVOICE DATE columnar
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if 'INVOICE DATE' in line.upper():
            for j in range(i + 1, min(i + 5, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _fmt(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    return None


def _extract_veit_ng(text: str) -> Optional[str]:
    """Veit/Waste Masters: DATE Mon-DD-YY format.
    Format: DATE Nov-09-25
    """
    m = re.search(r'DATE\s+([A-Z][a-z]{2})-(\d{2})-(\d{2})', text, re.I)
    if m:
        month_num = MONTH_MAP.get(m.group(1).lower())
        if month_num:
            return _fmt(month_num, int(m.group(2)), int(m.group(3)))
    # Fallback: INVOICE DATE columnar
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if 'INVOICE DATE' in line.upper():
            for j in range(i + 1, min(i + 5, len(lines))):
                m2 = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m2:
                    return _fmt(int(m2.group(1)), int(m2.group(2)), int(m2.group(3)))
    return None


def _extract_waste_disposal_ng(text: str) -> Optional[str]:
    """Waste Disposal AZ: Date Billed: MM/DD/YYYY.
    Format: Date Billed: 08/04/2025
    """
    return _try_mdy(text, r'Date\s*Billed[:\s]+(\d{1,2})[/\-](\d{1,2})[/\-](\d{4})', re.I)


def _extract_cockeys_ng(text: str) -> Optional[str]:
    """Cockey's: DATE with garbled month names.
    Format 1: DATE J ul 31, 2025 (space in month name)
    Format 2: DATE Nov 30. 2025 (period instead of comma)
    Format 3: DATE on standalone line, no date (column header)
              then Mon DD, YYYY or Jun 30, 2025 elsewhere
    """
    # Handle garbled month: J ul, A ug, J an, etc.
    m = re.search(r'DATE\s+([A-Z])\s*([a-z]{1,2})\s+(\d{1,2})[.,]?\s*(\d{4})', text)
    if m:
        month_str = (m.group(1) + m.group(2)).lower()
        month_num = MONTH_MAP.get(month_str)
        if month_num:
            return _fmt(month_num, int(m.group(3)), int(m.group(4)))
    # Standard DATE Month DD, YYYY (also handles period: Nov 30. 2025)
    m = re.search(r'DATE\s+([A-Za-z]+)\s+(\d{1,2})[.,]?\s*(\d{4})', text, re.I)
    if m:
        month_num = MONTH_MAP.get(m.group(1).lower()[:3])
        if month_num:
            return _fmt(month_num, int(m.group(2)), int(m.group(3)))
    # Month name date anywhere: Jun 30, 2025 or January 15, 2025
    m = re.search(r'\b(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\w*\s+(\d{1,2}),?\s*(\d{4})', text, re.I)
    if m:
        month_num = MONTH_MAP.get(m.group(1).lower()[:3])
        if month_num:
            result = _fmt(month_num, int(m.group(2)), int(m.group(3)))
            if result:
                return result
    # Fallback: INVOICE DATE columnar
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if 'INVOICE DATE' in line.upper() or line.strip().upper() == 'DATE':
            for j in range(i + 1, min(i + 5, len(lines))):
                m2 = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m2:
                    return _fmt(int(m2.group(1)), int(m2.group(2)), int(m2.group(3)))
    # Service period start
    m = re.search(r'(\d{2})/(\d{2})/(\d{2,4})\s*-\s*\d{2}/\d{2}/\d{2,4}', text)
    if m:
        return _fmt(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    return None


def _extract_republic_ng(text: str) -> Optional[str]:
    """Republic Services: Invoice Date with garbled month, fallback to other dates.
    Garbled: Invoice Date satiuaty tS, 2025
    Fallback: Month name dates, Past Due on MM/DD/YY
    """
    # Standard Invoice Date: MM/DD/YYYY
    result = _try_mdy(text, r'Invoice\s*Date[:\s]+(\d{1,2})[/\-](\d{1,2})[/\-](\d{4})', re.I)
    if result:
        return result
    result = _try_mdy(text, r'Invoice\s*Date[:\s]+(\d{1,2})[/\-](\d{1,2})[/\-](\d{2})', re.I)
    if result:
        return result
    # Month name: Invoice Date: January 15, 2025
    m = re.search(r'Invoice\s*Date[:\s]+([A-Za-z]+)\s+(\d{1,2}),?\s*(\d{4})', text, re.I)
    if m:
        month_num = MONTH_MAP.get(m.group(1).lower()[:3])
        if month_num:
            return _fmt(month_num, int(m.group(2)), int(m.group(3)))
    # Garbled Invoice Date with month name elsewhere in the text
    # Look for standalone Month DD, YYYY pattern (first occurrence)
    m = re.search(r'\b(January|February|March|April|May|June|July|August|September|October|November|December)\s+(\d{1,2}),?\s*(\d{4})', text, re.I)
    if m:
        month_num = MONTH_MAP.get(m.group(1).lower()[:3])
        if month_num:
            result = _fmt(month_num, int(m.group(2)), int(m.group(3)))
            if result:
                return result
    # Statement Date: MM/DD/YYYY
    result = _try_mdy(text, r'Statement\s*Date[:\s]+(\d{1,2})[/\-](\d{1,2})[/\-](\d{4})', re.I)
    if result:
        return result
    # Billing Period start date
    result = _try_mdy(text, r'(?:Billing|Service)\s*Period[:\s]+(\d{1,2})[/\-](\d{1,2})[/\-](\d{4})', re.I)
    if result:
        return result
    result = _try_mdy(text, r'(?:Billing|Service)\s*Period[:\s]+(\d{1,2})[/\-](\d{1,2})[/\-](\d{2})', re.I)
    if result:
        return result
    # Past Due on MM/DD/YY
    result = _try_mdy(text, r'Past\s+Due\s+on\s+(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})', re.I)
    if result:
        return result
    return None


def _extract_nws_ng(text: str) -> Optional[str]:
    """National Waste Services: date | invoice# or date invoice#.
    Format 1: 1/1/2025 | 1817118A (single month)
    Format 2: Multi-month - first valid M/D/YYYY in text
    Garbled: 9/1/7202 (year garbled)
    """
    # Date | invoice# or date invoice#
    m = re.search(r'(\d{1,2})/(\d{1,2})/(\d{4})\s*\|?\s*\d{7,8}[A-Z]?\b', text)
    if m:
        result = _fmt(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        if result:
            return result
    # Garbled date: 41/2025 (missing day sep)
    m = re.search(r'(\d{1,2})(\d{1})/(\d{4})\s+\d{7,8}[A-Z]?\b', text)
    if m:
        result = _fmt(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        if result:
            return result
    # Find first valid M/D/YYYY anywhere (for multi-month invoices)
    for m in re.finditer(r'(\d{1,2})/(\d{1,2})/(\d{4})', text):
        result = _fmt(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        if result:
            return result
    # Generic Invoice Date fallback
    result = _try_mdy(text, r'Invoice\s*Date[:\s]+(\d{1,2})[/\-](\d{1,2})[/\-](\d{4})', re.I)
    if result:
        return result
    return None


def _extract_parish_ng(text: str) -> Optional[str]:
    """Parish Disposal: INVOICE # DATE ... header, date on next line.
    Format: INVOICE # DATE TOTAL DUE DUE DATE ENCLOSED
            68492   02/15/2025  $xxx  03/02/2025  $xxx
    """
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if re.search(r'INVOICE\s*#\s+DATE', line, re.I):
            # Next lines: invoice# date amount...
            for j in range(i + 1, min(i + 5, len(lines))):
                m = re.search(r'\d{4,7}\s+(\d{1,2})/(\d{1,2})/(\d{4})', lines[j])
                if m:
                    return _fmt(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    # Standard Date: or Invoice Date:
    result = _try_mdy(text, r'(?:Invoice\s*)?Date[:\s]+(\d{1,2})[/\-](\d{1,2})[/\-](\d{4})', re.I)
    if result:
        return result
    return None


def _extract_burgmeiers_ng(text: str) -> Optional[str]:
    """Burgmeier's: Invoice Date DD Month, YYYY.
    Format: Invoice Date 07 May, 2025 (day before month)
    Also: INVDATE MM/DD/YY
    """
    # DD Month, YYYY after Invoice Date
    m = re.search(r'Invoice\s*Date\s+(\d{1,2})\s+([A-Za-z]+),?\s*(\d{4})', text, re.I)
    if m:
        month_num = MONTH_MAP.get(m.group(2).lower()[:3])
        if month_num:
            return _fmt(month_num, int(m.group(1)), int(m.group(3)))
    # INVDATE MM/DD/YY
    result = _try_mdy(text, r'INVDATE\s+(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})', re.I)
    if result:
        return result
    # INV DATE columnar
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if 'INV DATE' in line.upper() or 'INVDATE' in line.upper():
            for j in range(i + 1, min(i + 5, len(lines))):
                m2 = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m2:
                    return _fmt(int(m2.group(1)), int(m2.group(2)), int(m2.group(3)))
    return None


def _extract_wb_waste_ng(text: str) -> Optional[str]:
    """WB Waste: Date after company name or in payment stub.
    Format: WB Waste Solutions 4/1/2025
    Stub: 150089231 4/1/2025 1301370702 $310.42
    Garbled: WB Waste Solutions 14/1/2024 (month > 12)
    Fallback: service period date 11/01/2024 - 11/30/2024
    """
    # After company name
    m = re.search(r'WB\s*Waste.*?(\d{1,2})/(\d{1,2})/(\d{4})', text, re.I)
    if m:
        result = _fmt(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        if result:
            return result
    # Payment stub: account date invoice amount
    m = re.search(r'\d{9}\s+(\d{1,2})/(\d{1,2})/(\d{4})\s+\d{10}', text)
    if m:
        result = _fmt(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        if result:
            return result
    # INVOICE DATE columnar
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if 'INVOICE DATE' in line.upper():
            for j in range(i + 1, min(i + 5, len(lines))):
                m2 = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m2:
                    return _fmt(int(m2.group(1)), int(m2.group(2)), int(m2.group(3)))
    # Fallback: first service period start date
    m = re.search(r'(\d{2})/(\d{2})/(\d{4})\s*-\s*\d{2}/\d{2}/\d{4}', text)
    if m:
        return _fmt(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    return None


def _extract_waste_connections_ng(text: str) -> Optional[str]:
    """Waste Connections: STATEMENT DATE or Invoice Date columnar.
    Format 1: STATEMENT DATE 5/1/2025 (inline)
    Format 2: Invoice Date column header, date on subsequent data lines
    Format 3: WC of Florida - DATE\\nInvoice Date Invoice # Reference...
              then data lines with dates: 7/8/25 ...
    """
    # STATEMENT DATE inline
    result = _try_mdy(text, r'STATEMENT\s*DATE\s+(\d{1,2})[/\-](\d{1,2})[/\-](\d{4})', re.I)
    if result:
        return result
    result = _try_mdy(text, r'STATEMENT\s*DATE\s+(\d{1,2})[/\-](\d{1,2})[/\-](\d{2})', re.I)
    if result:
        return result
    # Invoice Date columnar - find header, then first date on data lines
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if re.search(r'Invoice\s*Date\s+Invoice\s*#', line, re.I):
            # Column header found - look for first date on data lines
            for j in range(i + 1, min(i + 20, len(lines))):
                # Skip non-data lines (empty, disclaimer, etc.)
                if lines[j].strip().startswith('*') or not lines[j].strip():
                    continue
                m = re.search(r'(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})', lines[j])
                if m:
                    r = _fmt(int(m.group(1)), int(m.group(2)), int(m.group(3)))
                    if r:
                        return r
    # Simple Invoice Date columnar
    for i, line in enumerate(lines):
        if re.search(r'Invoice\s*Date', line, re.I) and 'Invoice #' not in line:
            for j in range(i + 1, min(i + 5, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\b', lines[j].strip())
                if m:
                    return _fmt(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    # Mon-DD-YY format (Dec-31-24)
    m = re.search(r'([A-Z][a-z]{2})-(\d{2})-(\d{2})', text)
    if m:
        month_num = MONTH_MAP.get(m.group(1).lower())
        if month_num:
            return _fmt(month_num, int(m.group(2)), int(m.group(3)))
    # BILLING PERIOD start date
    result = _try_mdy(text, r'BILLING\s*PERIOD\s*=?\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{4})', re.I)
    if result:
        return result
    return None


def _extract_unique_sanitation_ng(text: str) -> Optional[str]:
    """Unique Sanitation: Date near invoice number, no label.
    Format: 71261808\\nnvoice\\n...\\n04/30/2025
    """
    # Near Invoice label
    m = re.search(r'(?:Invoice|nvoice)\b.*?(\d{1,2})/(\d{1,2})/(\d{4})', text, re.I | re.DOTALL)
    if m:
        return _fmt(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    # Standalone date in first 5 lines
    lines = text.split('\n')
    for line in lines[:10]:
        m = re.search(r'(\d{1,2})/(\d{1,2})/(\d{4})', line)
        if m:
            result = _fmt(int(m.group(1)), int(m.group(2)), int(m.group(3)))
            if result:
                return result
    return None


def _extract_arc_ng(text: str) -> Optional[str]:
    """The Arc of The St Johns: Standalone MM/DD/YYYY near top.
    Format: 04/01/2025 (standalone, no label)
    """
    lines = text.split('\n')
    for line in lines[:15]:
        m = re.match(r'^\s*(\d{2})/(\d{2})/(\d{4})\s*$', line.strip())
        if m:
            return _fmt(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        # Also try: date followed by other text on same line
        m = re.search(r'^(\d{2})/(\d{2})/(\d{4})\b', line.strip())
        if m:
            result = _fmt(int(m.group(1)), int(m.group(2)), int(m.group(3)))
            if result:
                return result
    return None


def _extract_tate_ng(text: str) -> Optional[str]:
    """Tate Services: Date near CUSTOMER NO or standalone.
    Format: CUSTOMER NO 010245\\n1020/2025 (garbled) or 10/30/2025
    """
    # Standard labels
    result = _try_mdy(text, r'Invoice\s*Date[:\s]+(\d{1,2})[/\-](\d{1,2})[/\-](\d{4})', re.I)
    if result:
        return result
    # Date on line after CUSTOMER NO
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if 'CUSTOMER NO' in line.upper():
            # Check same line for date
            m = re.search(r'(\d{1,2})/(\d{1,2})/(\d{4})', line)
            if m:
                return _fmt(int(m.group(1)), int(m.group(2)), int(m.group(3)))
            # Check next line
            if i + 1 < len(lines):
                m = re.search(r'(\d{1,2})/(\d{1,2})/(\d{4})', lines[i + 1])
                if m:
                    return _fmt(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    # First MM/DD/YYYY in text
    m = re.search(r'(\d{1,2})/(\d{1,2})/(\d{4})', text)
    if m:
        return _fmt(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    return None


def _extract_rumpke_ng(text: str) -> Optional[str]:
    """Rumpke: Date: with possible OCR garble.
    Format: Date: (14/02/25 (garbled, should be 04/02/25)
    Garbled month > 12 → use service period start as fallback
    """
    # Standard Date: MM/DD/YY
    result = _try_mdy(text, r'Date:\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})', re.I)
    if result:
        return result
    # Garbled: Date: (NN/DD/YY - strip paren
    m = re.search(r'Date:\s*\(?(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})', text, re.I)
    if m:
        result = _fmt(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        if result:
            return result
    # Invoice Date columnar
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if 'INVOICE DATE' in line.upper():
            for j in range(i + 1, min(i + 5, len(lines))):
                m2 = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m2:
                    return _fmt(int(m2.group(1)), int(m2.group(2)), int(m2.group(3)))
    # Service period start (first valid date in service lines)
    for m in re.finditer(r'(\d{2})/(\d{2})/(\d{2,4})', text):
        result = _fmt(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        if result:
            return result
    return None


def _extract_casella_ng(text: str) -> Optional[str]:
    """Casella: Invoice Date on line before, then invoice# + date on next line.
    Format: Invoice # Invoice Date
            5451664 9/02/25
    """
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if 'Invoice Date' in line or 'Invoice date' in line:
            # Check next few lines for date
            for j in range(i + 1, min(i + 5, len(lines))):
                m = re.search(r'(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})', lines[j])
                if m:
                    return _fmt(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    # Inline: Invoice Date: M/DD/YY
    result = _try_mdy(text, r'Invoice\s*Date[:\s]+(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})', re.I)
    if result:
        return result
    return None


def _extract_robinson_ng(text: str) -> Optional[str]:
    """Robinson Waste: DATE MM/DD/YYYY (may be garbled).
    Format: DATE 10/31/2025
    Garbled: DATE 98/31/2025 → use DUE DATE as reference
    """
    # Standard DATE label
    result = _try_mdy(text, r'\bDATE\s+(\d{1,2})/(\d{1,2})/(\d{4})', 0)
    if result:
        return result
    # Garbled first digit (98/31/2025 → 08/31/2025)
    m = re.search(r'\bDATE\s+(\d{2})/(\d{1,2})/(\d{4})', text)
    if m:
        month = int(m.group(1))
        day = int(m.group(2))
        year = int(m.group(3))
        # If month > 12, try fixing first digit
        if month > 12:
            month = month % 10  # Take last digit: 98 → 8
            if month == 0:
                month = 10
        return _fmt(month, day, year)
    # DUE DATE as fallback
    result = _try_mdy(text, r'DUE\s*DATE[:\s]+(\d{1,2})/(\d{1,2})/(\d{4})', 0)
    if result:
        return result
    return None


def _extract_cm_topsoil_ng(text: str) -> Optional[str]:
    """C&M Topsoil: DATE on label line, date on next line.
    Format: ___DATE __INVOICE #
            10/27/2025 196953
    """
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if 'DATE' in line.upper() and 'INVOICE' in line.upper():
            for j in range(i + 1, min(i + 5, len(lines))):
                m = re.search(r'(\d{1,2})/(\d{1,2})/(\d{4})', lines[j])
                if m:
                    return _fmt(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    # Generic Date label
    result = _try_mdy(text, r'Date[:\s]+(\d{1,2})[/\-](\d{1,2})[/\-](\d{4})', re.I)
    if result:
        return result
    return None


def _extract_aspen_ng(text: str) -> Optional[str]:
    """Aspen Waste: invoice Date multiline then date.
    Format: invoice Date\\n\\nASPEN WASTE...\\n10/03/2025
    Also: Date due MM/DD/YYYY
    """
    # Standard Invoice Date inline
    result = _try_mdy(text, r'Invoice\s*Date[:\s]+(\d{1,2})[/\-](\d{1,2})[/\-](\d{4})', re.I)
    if result:
        return result
    # Invoice Date columnar
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if re.search(r'invoice\s*date', line, re.I):
            for j in range(i + 1, min(i + 8, len(lines))):
                m = re.search(r'(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})', lines[j])
                if m:
                    r = _fmt(int(m.group(1)), int(m.group(2)), int(m.group(3)))
                    if r:
                        return r
    return None


def _extract_atlantic_ng(text: str) -> Optional[str]:
    """Atlantic Waste: INVOICE DATE inline.
    Format: INVOICE DATE 12/09/2024 (with address text between on same line)
    """
    result = _try_mdy(text, r'INVOICE\s*DATE\s+(\d{1,2})[/\-](\d{1,2})[/\-](\d{4})', re.I)
    if result:
        return result
    # Columnar: INVOICE DATE on header, date on next line
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if 'INVOICE DATE' in line.upper():
            # Same line - find date anywhere
            m = re.search(r'(\d{1,2})/(\d{1,2})/(\d{4})', line)
            if m:
                return _fmt(int(m.group(1)), int(m.group(2)), int(m.group(3)))
            for j in range(i + 1, min(i + 3, len(lines))):
                m = re.search(r'(\d{1,2})/(\d{1,2})/(\d{4})', lines[j])
                if m:
                    return _fmt(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    return None


def _extract_vanderlind_ng(text: str) -> Optional[str]:
    """Vanderlind Recycling: Date: with garbled month name.
    Format: Date: J an 20, 2025
    """
    # Garbled month: J an, F eb, etc.
    m = re.search(r'Date:\s*([A-Z])\s*([a-z]{1,2})\s+(\d{1,2}),?\s*(\d{4})', text)
    if m:
        month_str = (m.group(1) + m.group(2)).lower()
        month_num = MONTH_MAP.get(month_str)
        if month_num:
            return _fmt(month_num, int(m.group(3)), int(m.group(4)))
    # Standard Date: Month DD, YYYY
    m = re.search(r'Date:\s*([A-Za-z]+)\s+(\d{1,2}),?\s*(\d{4})', text, re.I)
    if m:
        month_num = MONTH_MAP.get(m.group(1).lower()[:3])
        if month_num:
            return _fmt(month_num, int(m.group(2)), int(m.group(3)))
    # Invoice Date
    result = _try_mdy(text, r'Invoice\s*Date[:\s]+(\d{1,2})[/\-](\d{1,2})[/\-](\d{4})', re.I)
    if result:
        return result
    return None


# =============================================================================
# Registration dict - overrides/supplements main additions
# =============================================================================

VENDOR_DATE_NG_FIXES = {
    'EDCO Disposal': {
        'format': 'account_code MM/DD/YY',
        'extract': _extract_edco_ng,
    },
    'KMG Hauling': {
        'format': 'payment_stub or INVOICE DATE columnar',
        'extract': _extract_kmg_ng,
    },
    'Veit': {
        'format': 'DATE Mon-DD-YY',
        'extract': _extract_veit_ng,
    },
    'Veit Disposal': {
        'format': 'DATE Mon-DD-YY',
        'extract': _extract_veit_ng,
    },
    'Waste Disposal': {
        'format': 'Date Billed: MM/DD/YYYY',
        'extract': _extract_waste_disposal_ng,
    },
    'Waste Disposal AZ': {
        'format': 'Date Billed: MM/DD/YYYY',
        'extract': _extract_waste_disposal_ng,
    },
    "Cockey's Enterprises": {
        'format': 'DATE Month DD, YYYY (garbled)',
        'extract': _extract_cockeys_ng,
    },
    'Republic Services': {
        'format': 'Invoice Date or fallback',
        'extract': _extract_republic_ng,
    },
    'National Waste Services': {
        'format': 'M/D/YYYY | invoice#',
        'extract': _extract_nws_ng,
    },
    'Parish Disposal': {
        'format': 'INVOICE # DATE header, date on next line',
        'extract': _extract_parish_ng,
    },
    "Burgmeier's Hauling": {
        'format': 'Invoice Date DD Month, YYYY',
        'extract': _extract_burgmeiers_ng,
    },
    'WB Waste Solutions': {
        'format': 'date after company name',
        'extract': _extract_wb_waste_ng,
    },
    'Waste Connections': {
        'format': 'STATEMENT DATE or Invoice Date columnar',
        'extract': _extract_waste_connections_ng,
    },
    'Unique Sanitation': {
        'format': 'date near invoice number',
        'extract': _extract_unique_sanitation_ng,
    },
    'Waste Masters': {
        'format': 'DATE Mon-DD-YY',
        'extract': _extract_veit_ng,
    },
    'Waste Masters Solutions': {
        'format': 'DATE Mon-DD-YY',
        'extract': _extract_veit_ng,
    },
    'The Arc of The St Johns': {
        'format': 'standalone MM/DD/YYYY',
        'extract': _extract_arc_ng,
    },
    'Tate Services': {
        'format': 'date near CUSTOMER NO',
        'extract': _extract_tate_ng,
    },
    'Rumpke': {
        'format': 'Date: MM/DD/YY',
        'extract': _extract_rumpke_ng,
    },
    'Casella': {
        'format': 'Invoice Date columnar',
        'extract': _extract_casella_ng,
    },
    'Robinson Waste': {
        'format': 'DATE MM/DD/YYYY',
        'extract': _extract_robinson_ng,
    },
    'C&M Topsoil': {
        'format': 'DATE label, date on next line',
        'extract': _extract_cm_topsoil_ng,
    },
    'Aspen Waste': {
        'format': 'Invoice Date multiline',
        'extract': _extract_aspen_ng,
    },
    'Atlantic Waste': {
        'format': 'INVOICE DATE inline',
        'extract': _extract_atlantic_ng,
    },
    'Vanderlind Recycling': {
        'format': 'Date: Month DD, YYYY',
        'extract': _extract_vanderlind_ng,
    },
}
