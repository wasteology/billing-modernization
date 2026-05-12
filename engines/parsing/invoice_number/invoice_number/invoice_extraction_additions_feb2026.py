"""
Invoice Extraction Additions - February 2026
Pattern fixes for NG Report invoice processing pipeline.
"""
import re
from typing import Optional


# ============================================================
# EXTRACTION FUNCTIONS
# ============================================================

def _extract_robinson_waste_fixed(text: str) -> Optional[str]:
    """Format: INVOICE NO. NNNNNNNNNN (10-digit, same or next line)
    Examples: 0000363705
    FIX: Original only checked next lines. Also check same line and handle
    garbled OCR where number appears with mixed chars.
    """
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if 'INVOICE NO' in line.upper():
            # Same line
            m = re.search(r'INVOICE\s*NO\.?\s*(\d{10})', line, re.I)
            if m:
                return m.group(1)
            # Next lines
            for j in range(i + 1, min(i + 5, len(lines))):
                val = lines[j].strip()
                if re.match(r'^\d{10}$', val):
                    return val
                m = re.search(r'(\d{10})', val)
                if m:
                    return m.group(1)
    # Fallback: look for Invoice # NNNNNNNNNN anywhere
    m = re.search(r'Invoice\s*#:?\s*(\d{10})', text, re.I)
    if m:
        return m.group(1)
    return None


def _extract_veit_invoice(text: str) -> Optional[str]:
    """Format: INVOICE NO. VM NNNNNNNNNN (VM prefix + 10-digit)
    Also: INVOICE NO. NNNNNNNNNN without prefix
    Examples: VM 0000692406
    """
    # With VM prefix
    m = re.search(r'INVOICE\s*NO\.?\s*(?:VM\s*)?(\d{10})', text, re.I)
    if m:
        return m.group(1)
    # Next line after INVOICE NO.
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if 'INVOICE NO' in line.upper():
            for j in range(i + 1, min(i + 3, len(lines))):
                val = lines[j].strip()
                m = re.match(r'(?:VM\s*)?(\d{10})$', val)
                if m:
                    return m.group(1)
    return None


def _extract_meridian_waste_fixed(text: str) -> Optional[str]:
    """Format: 7-digit after date in header, or after Invoice #
    Examples: 6225428, 6912577
    FIX: Original only checked Invoice # label. Also check header line
    where invoice # appears after date: MM/DD/YYYY NNNNNNN
    """
    # Standard Invoice # format
    m = re.search(r'Invoice\s*#:?\s*(\d{7})', text, re.I)
    if m:
        return m.group(1)
    # Header format: date followed by 7-digit
    m = re.search(r'\d{2}/\d{2}/\d{4}\s+(\d{7})\b', text)
    if m:
        return m.group(1)
    # Next line after Invoice #
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if 'Invoice #' in line or 'Invoice#' in line:
            for j in range(i + 1, min(i + 3, len(lines))):
                m = re.search(r'(\d{7})', lines[j])
                if m:
                    return m.group(1)
    return None


def _extract_tate_services_fixed(text: str) -> Optional[str]:
    """Format: 10-digit standalone (no Invoice label) or Invoice No. NNNNNNNNNN
    Examples: 0000173482, 0000235059
    FIX: Original required Invoice No. label. Tate invoices often have the
    10-digit number standalone between CUSTOMER NO and CUSTOMER PO lines.
    Also found in payment stub: account date invoice# amount
    """
    # Standard Invoice No. label
    m = re.search(r'Invoice\s*No\.?:?\s*(\d{9,11})', text, re.I)
    if m:
        return m.group(1)
    # Standalone: look for 10-digit number near date/customer lines
    lines = text.split('\n')
    for i, line in enumerate(lines):
        val = line.strip().lstrip('; ')
        if re.match(r'^\d{10}$', val):
            return val
    # Payment stub format: account date 10-digit-invoice amount
    # e.g.: 010245 10/20/2025 0000229296 $460.00
    m = re.search(r'\d{6}\s+\d{1,2}/\d{1,2}/\d{4}\s+(\d{10})\s+\$', text)
    if m:
        return m.group(1)
    return None


def _extract_kmg_hauling_fixed(text: str) -> Optional[str]:
    """Format: 10-digit standalone or after INVOICE NO
    Examples: 0000483416, 0000498827
    FIX: Original only checked after INVOICE NO. KMG invoices often have
    standalone 10-digit number in header without label.
    Also check payment stub: account date invoice amount
    """
    # Standard INVOICE NO label
    lines = text.split('\n')
    for i, line in enumerate(lines[:20]):
        if 'INVOICE NO' in line.upper():
            for j in range(i + 1, min(i + 4, len(lines))):
                val = lines[j].strip()
                if re.match(r'^\d{10}$', val):
                    return val
    # Standalone 10-digit in header area
    for line in lines[:15]:
        val = line.strip()
        if re.match(r'^\d{10}$', val):
            return val
    # Payment stub: account date invoice amount
    # e.g.: 006238 10/15/2025 0000493944 $843.37
    m = re.search(r'\d{6}\s+\d{1,2}/\d{1,2}/\d{4}\s+(\d{10})\s+\$', text)
    if m:
        return m.group(1)
    return None


def _extract_unique_sanitation_invoice(text: str) -> Optional[str]:
    """Format: 8-digit near Invoice text or in payment stub
    Examples: 71261808, 21257627
    Payment stub format: WAST342362 21257627 10/31/2024 THIS AMOUNT
    """
    # Near "Invoice" label
    m = re.search(r'(\d{8})\s*\n\s*(?:n?[Ii]nvoice|INVOICE)', text)
    if m:
        return m.group(1)
    # Same line as company name
    m = re.search(r'Unique Sanitation.*?(\d{8})', text, re.I)
    if m:
        return m.group(1)
    # Generic Invoice # format
    m = re.search(r'Invoice\s*(?:#|No\.?|Number)?:?\s*(\d{7,10})', text, re.I)
    if m:
        return m.group(1)
    # Payment stub: account invoice_number date
    # e.g.: WAST342362 21257627 10/31/2024 THIS AMOUNT
    m = re.search(r'WAST\d+\s+(\d{8})\s+\d{2}/\d{2}/\d{4}', text)
    if m:
        return m.group(1)
    return None


def _extract_parish_disposal_fixed(text: str) -> Optional[str]:
    """Format: INVOICE # header, then number on next line
    Examples: 68492, 66918
    FIX: Original only handled same-line. Parish invoices have the number
    on the line below the INVOICE # header row.
    """
    lines = text.split('\n')
    # Look for INVOICE # as column header, then number on next line
    for i, line in enumerate(lines):
        if re.search(r'INVOICE\s*#', line, re.I):
            for j in range(i + 1, min(i + 3, len(lines))):
                # Number followed by date: 68492 02/15/2025
                m = re.match(r'\s*(\d{5,7})\s+\d{2}/\d{2}/\d{4}', lines[j])
                if m:
                    return m.group(1)
                # Standalone number
                m = re.match(r'\s*(\d{5,7})\s', lines[j])
                if m:
                    return m.group(1)
    # Same line: Invoice # NNNNN (only if followed immediately by digits)
    m = re.search(r'Invoice\s*#\s*(\d{5,7})\b', text, re.I)
    if m:
        return m.group(1)
    return None


def _extract_burgmeiers_invoice_fixed(text: str) -> Optional[str]:
    """Format: Invoice# NNNN (4-digit) or Invoice NNNN
    Examples: 2877, 6655
    FIX: Original required 5-10 digits. Burgmeier's uses 4-digit.
    Also handles garbled OCR like 'Invoice#t' or 'Invoice '
    """
    # Handle garbled # like Invoice#t, Invoice# , Invoice
    m = re.search(r'Invoice\s*#?\w?\s+(\d{4,10})', text, re.I)
    if m:
        val = m.group(1)
        if not re.match(r'^20\d{2}$', val):
            return val
    # Also try without space after Invoice
    m = re.search(r'Invoice\s*#?\s*(\d{4,10})', text, re.I)
    if m:
        val = m.group(1)
        if not re.match(r'^20\d{2}$', val):
            return val
    return None


def _extract_jamaica_ash_invoice(text: str) -> Optional[str]:
    """Format: INVOICE# NNXNNNNN or NLXNNNNN (alphanumeric with possible OCR garble)
    Examples: 52X38251, 54X00514, 5AX00740
    Pattern: digit + alphanumeric + X + 5-digit
    """
    # With INVOICE label (handles —, #, garbled chars)
    m = re.search(r'INVOICE\s*[#—\-§]?\s*[#]?\s*(\d[A-Z0-9][Xx]\d{5})', text, re.I)
    if m:
        return m.group(1).upper()
    # Without label - alphanumeric+X+5digit pattern
    m = re.search(r'\b(\d[A-Z0-9][Xx]\d{5})\b', text)
    if m:
        return m.group(1).upper()
    return None


def _extract_atlantic_waste_invoice_fixed(text: str) -> Optional[str]:
    """Format: INVOICE NO ... SWO prefix + digits or 7-digit numeric
    Examples: SWO0015851-1, 1044333
    FIX: Original only matched 7-digit numeric. Atlantic Waste uses SWO prefix.
    """
    # SWO format (same or next line)
    m = re.search(r'INVOICE\s*NO\.?\s*(SWO\d+-\d+)', text, re.I)
    if m:
        return m.group(1)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if 'INVOICE NO' in line.upper():
            for j in range(i + 1, min(i + 3, len(lines))):
                m = re.search(r'(SWO\d+-\d+)', lines[j])
                if m:
                    return m.group(1)
    # Original 7-digit numeric
    m = re.search(r'Invoice\s*Number\s*(\d{7})', text, re.I)
    if m:
        return m.group(1)
    return None


def _extract_national_waste_services_invoice(text: str) -> Optional[str]:
    """Format: DATE | NNNNNNN[A] on header line near phone/fax
    Examples: 1817118A, 1811026A, 17981244
    NWS invoices have the invoice # after the date on the phone/fax line.
    Handles garbled dates like 41/2025 or 9/1/7202
    """
    # Pattern: date or garbled date followed by invoice number
    # Standard: 1/1/2025 | 1817118A or 1/1/2025 1817118A
    m = re.search(r'\d{1,2}/\d{1,2}/\d{4}\s*\|?\s*(\d{7,8}[A-Z]?)\b', text)
    if m:
        return m.group(1)
    # Garbled date: 41/2025 1790128A (missing day separator)
    m = re.search(r'\d{2,4}/\d{4}\s+(\d{7,8}[A-Z]?)\b', text)
    if m:
        return m.group(1)
    # Generic fallback
    m = re.search(r'Invoice\s*(?:#|No\.?|Number)?:?\s*(\d{5,10}[A-Z]?)', text, re.I)
    if m:
        return m.group(1)
    return None


def _extract_universal_waste_fixed(text: str) -> Optional[str]:
    """Format: 10-digit after Invoice Number label or in payment stub
    Examples: 0003898670, 0003699650
    FIX: Original only checked Invoice Number label + columnar.
    Also check payment stub: account - invoice_number
    """
    lines = text.split('\n')
    # Pattern 1: Invoice Number header with value on nearby lines
    for i, line in enumerate(lines):
        if 'Invoice Number' in line:
            # Same line
            m = re.search(r'Invoice\s*Number:?\s*(\d{10})', line, re.I)
            if m:
                return m.group(1)
            # Value on subsequent lines (columnar format)
            for j in range(i + 1, min(i + 10, len(lines))):
                val = lines[j].strip()
                if re.match(r'^\d{10}$', val):
                    return val
    # Pattern 2: Payment stub: account - invoice_number
    # e.g.: 272953 - 0003699650
    m = re.search(r'\d{6}\s*-\s*(\d{10})', text)
    if m:
        return m.group(1)
    return None


# ============================================================
# VENDOR CONFIGURATIONS
# ============================================================

VENDOR_ADDITIONS_FEB2026 = {
    'Robinson Waste': {
        'format': 'NNNNNNNNNN',
        'examples': ['0000363705'],
        'extract': _extract_robinson_waste_fixed
    },
    'Veit': {
        'format': 'VM NNNNNNNNNN',
        'examples': ['0000692406'],
        'extract': _extract_veit_invoice
    },
    'Veit Disposal': {
        'format': 'VM NNNNNNNNNN',
        'examples': ['0000692406'],
        'extract': _extract_veit_invoice
    },
    'Meridian Waste': {
        'format': 'NNNNNNN',
        'examples': ['6225428'],
        'extract': _extract_meridian_waste_fixed
    },
    'Tate Services': {
        'format': 'NNNNNNNNNN',
        'examples': ['0000173482'],
        'extract': _extract_tate_services_fixed
    },
    'KMG Hauling': {
        'format': 'NNNNNNNNNN',
        'examples': ['0000483416'],
        'extract': _extract_kmg_hauling_fixed
    },
    'Unique Sanitation': {
        'format': 'NNNNNNNN',
        'examples': ['71261808'],
        'extract': _extract_unique_sanitation_invoice
    },
    'Parish Disposal': {
        'format': 'NNNNN',
        'examples': ['68492', '66918'],
        'extract': _extract_parish_disposal_fixed
    },
    "Burgmeier's Hauling": {
        'format': 'NNNN',
        'examples': ['2877', '6655'],
        'extract': _extract_burgmeiers_invoice_fixed
    },
    'Jamaica Ash': {
        'format': 'NNxNNNNN',
        'examples': ['52X38251', '54X00514'],
        'extract': _extract_jamaica_ash_invoice
    },
    'Jamaica Ash & Rubbish': {
        'format': 'NNxNNNNN',
        'examples': ['52X38251', '54X00514'],
        'extract': _extract_jamaica_ash_invoice
    },
    'Atlantic Waste': {
        'format': 'SWONNNNNNN-N',
        'examples': ['SWO0015851-1'],
        'extract': _extract_atlantic_waste_invoice_fixed
    },
    'National Waste Services': {
        'format': 'NNNNNNN',
        'examples': [],
        'extract': _extract_national_waste_services_invoice
    },
    'Universal Waste': {
        'format': 'NNNNNNNNNN',
        'examples': ['0003898670', '0003699650'],
        'extract': _extract_universal_waste_fixed
    },
}


def register_additions(vendor_invoices: dict):
    """Register Feb 2026 additions to the main VENDOR_INVOICES dict."""
    vendor_invoices.update(VENDOR_ADDITIONS_FEB2026)
