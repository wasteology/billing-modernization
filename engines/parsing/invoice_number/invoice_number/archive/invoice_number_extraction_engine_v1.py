"""
Invoice Number Extraction Engine v1.0
Extracts invoice numbers from invoice OCR text.

Designed to work with vendor_detection_module.py as part of deterministic 
invoice matching pipeline.

Usage:
    1. First detect vendor using vendor_detection_module.detect_vendor()
    2. Then extract invoice number using extract_invoice_number(vendor_name, text)

DETERMINISTIC RULES:
- Each vendor has explicit extraction logic
- Returns invoice number OR None (no guessing)
- Pattern must match exactly or extraction fails

INVOICE NUMBER FORMAT PATTERNS BY VENDOR:
===========================================
- Waste Management: 10-digit numeric (1003677678)
- Republic Services: DDDD-NNNNNNNNN (0176-007823583)
- GFL: Prefix + digits (UK0000449634)
- Rumpke: 7-digit numeric (3042988)
- Waste Pro: 10-digit numeric (0002377717)
- Casella: 7-digit numeric (5538229)
- Waste Connections: Alphanumeric with district code (8249066T300)
- Meridian Waste: 7-digit numeric (6912577)
- Tiger Sanitation: 7-digit numeric (1153224)
- Athens Services: 8-digit numeric (20284083)
- FCC Environmental: 6-7 digit numeric (1589436)
- Robinson Waste: 10-digit with leading zeros (0000363705)
- Anytime Waste: 6-digit numeric (228047)
- Lightning Disposal: 10-digit with leading zeros (0000857784)
- All Waste: 6-digit numeric (425482)
- Granger Waste: 8-digit numeric (29584359)

Maintained by: Wasteology
Last updated: December 2024
"""
import re
from typing import Optional, Dict, Any, List


# ============================================================
# HELPER FUNCTIONS
# ============================================================

def _normalize_text(text: str) -> str:
    """
    Normalize OCR text line breaks.
    OCR output may use literal '\\n' (escaped) or actual newlines.
    This function converts both to actual newlines for consistent processing.
    """
    # First replace literal \\n with actual newlines
    text = text.replace('\\n', '\n')
    return text


def _split_lines(text: str) -> list:
    """Split text into lines, handling both \\n and actual newlines."""
    normalized = _normalize_text(text)
    return normalized.split('\n')


# ============================================================
# VENDOR INVOICE CONFIGURATIONS
# ============================================================

VENDOR_INVOICES = {}


# ============================================================
# NAVUSOFT-STYLE VENDORS
# These vendors use NavuSoft billing platform with consistent format:
# Invoice # appears at top of document in header block
# ============================================================

def _extract_navusoft_invoice(text: str, expected_digits: tuple = (6, 10)) -> Optional[str]:
    """
    Generic NavuSoft format extractor.
    NavuSoft invoices have a header block with INVOICE # followed by value.
    Format: INVOICE #\nAMOUNT\nACCOUNT #\nDATE\n<invoice_num>\n...
    
    Args:
        text: OCR text
        expected_digits: (min_digits, max_digits) tuple for validation
    """
    lines = _split_lines(text)
    
    # Pattern 1: Invoice number at line 0 (common NavuSoft format)
    if len(lines) > 0:
        val = lines[0].strip()
        if re.match(r'^\d{%d,%d}$' % expected_digits, val):
            return val
    
    # Pattern 2: After "INVOICE #" header (search first 20 lines)
    for i, line in enumerate(lines[:20]):
        if 'INVOICE #' in line.upper() or 'INVOICE#' in line.upper():
            # Check same line after label
            match = re.search(r'INVOICE\s*#:?\s*(\d{%d,%d})' % expected_digits, line, re.I)
            if match:
                return match.group(1)
            # Check next few lines
            for j in range(i+1, min(i+5, len(lines))):
                val = lines[j].strip()
                if re.match(r'^\d{%d,%d}$' % expected_digits, val):
                    return val
    
    return None


def _extract_anytime_waste_invoice(text: str) -> Optional[str]:
    """Format: 6-digit numeric
    Examples: 228047, 231573
    """
    return _extract_navusoft_invoice(text, (6, 6))

VENDOR_INVOICES['Anytime Waste'] = {
    'format': 'NNNNNN',
    'examples': ['228047', '231573', '229856'],
    'extract': _extract_anytime_waste_invoice
}


def _extract_fcc_environmental_invoice(text: str) -> Optional[str]:
    """Format: 6-7 digit numeric OR FCCXX/YY/NNNNNNN format
    Multiple regions use different formats:
    - NavuSoft regions: 6-7 digit at line 1 (e.g., 1598198)
    - Tampa region: FCCFL/25/1087352 format with various layouts
    Examples: 1589436, 270894, FCCFL/25/1087352
    """
    lines = _split_lines(text)
    
    # Pattern 1: Tampa/FL alphanumeric format - search anywhere in first 15 lines
    for i, line in enumerate(lines[:15]):
        match = re.search(r'(FCC[A-Z]{2}/\d{2}/\d+)', line)
        if match:
            return match.group(1)
    
    # Pattern 2: NavuSoft format - check lines 0-2 for 6-7 digit number
    for i in range(min(3, len(lines))):
        val = lines[i].strip()
        if re.match(r'^\d{6,7}$', val):
            return val
    
    # Pattern 3: After "INVOICE #" header (NavuSoft)
    for i, line in enumerate(lines[:25]):
        if 'INVOICE #' in line.upper():
            match = re.search(r'INVOICE\s*#:?\s*(\d{6,7})', line, re.I)
            if match:
                return match.group(1)
            # Check next lines for columnar format
            for j in range(i+1, min(i+8, len(lines))):
                val = lines[j].strip()
                if re.match(r'^\d{6,7}$', val):
                    return val
    
    return None

VENDOR_INVOICES['FCC Environmental'] = {
    'format': 'NNNNNNN',
    'examples': ['1589436', '270894', '1587321'],
    'extract': _extract_fcc_environmental_invoice
}


def _extract_tiger_sanitation_invoice(text: str) -> Optional[str]:
    """Format: 7-digit numeric
    Examples: 1153224, 1148756, 1242381
    
    OCR shows: INVOICE NO (header) followed by 7-digit value nearby
    """
    lines = _split_lines(text)
    
    # Pattern 1: After "INVOICE NO" header - search nearby lines
    for i, line in enumerate(lines):
        if 'INVOICE NO' in line.upper():
            # Check next 5 lines for 7-digit number
            for j in range(i+1, min(i+6, len(lines))):
                val = lines[j].strip()
                if re.match(r'^\d{7}$', val):
                    return val
    
    # Pattern 2: Direct pattern match
    match = re.search(r'INVOICE\s*NO\.?\s*(\d{7})', text, re.I)
    if match:
        return match.group(1)
    
    return None

VENDOR_INVOICES['Tiger Sanitation'] = {
    'format': 'NNNNNNN',
    'examples': ['1153224', '1148756', '1152089'],
    'extract': _extract_tiger_sanitation_invoice
}


def _extract_hamilton_alliance_invoice(text: str) -> Optional[str]:
    """Format: 5-digit numeric (NavuSoft columnar)
    Examples: 16992, 15847
    
    OCR shows columnar format:
    INVOICE #
    AMOUNT
    ACCOUNT #
    DATE
    QUICK PAY CODE
    <invoice_value>  <- 5 lines after INVOICE #
    """
    lines = _split_lines(text)
    
    # Pattern 1: NavuSoft columnar format - INVOICE # header with value 5 lines later
    for i, line in enumerate(lines):
        if line.strip() == 'INVOICE #':
            if i+5 < len(lines):
                val = lines[i+5].strip()
                if re.match(r'^\d{5,6}$', val):
                    return val
    
    # Pattern 2: Search first 15 lines for 5-6 digit standalone number
    for i, line in enumerate(lines[:15]):
        if 'INVOICE #' in line.upper():
            for j in range(i+1, min(i+8, len(lines))):
                val = lines[j].strip()
                if re.match(r'^\d{5,6}$', val):
                    return val
    
    return None

VENDOR_INVOICES['Hamilton Alliance'] = {
    'format': 'NNNNN',
    'examples': ['16992', '15847', '16123'],
    'extract': _extract_hamilton_alliance_invoice
}


def _extract_frontier_waste_invoice(text: str) -> Optional[str]:
    """Format: 7-digit numeric (NavuSoft)
    Examples: 7877246, 7856321
    """
    return _extract_navusoft_invoice(text, (7, 7))

VENDOR_INVOICES['Frontier Waste'] = {
    'format': 'NNNNNNN',
    'examples': ['7877246', '7856321', '7865432'],
    'extract': _extract_frontier_waste_invoice
}


# ============================================================
# TIER 1: HIGH VOLUME VENDORS (>2,000 invoices)
# ============================================================

def _extract_waste_connections_invoice(text: str) -> Optional[str]:
    """Format: NNNNNNNXDDD (digits + letter + district code)
    Examples: 8249066T300, 177355066U037, 14281304W319
    
    OCR shows columnar format:
    ACCOUNT NO.
    INVOICE NO.
    STATEMENT DATE
    DUE DATE
    BILLING PERIOD
    <account_value>
    <invoice_value>  <- 5 lines after INVOICE NO.
    ...
    """
    lines = _split_lines(text)
    
    # Pattern 1: Columnar format - find INVOICE NO. header and get value 5 lines later
    for i, line in enumerate(lines):
        if line.strip() == 'INVOICE NO.' or line.strip() == 'INVOICE NO':
            # Check if this is the columnar header format (next line is STATEMENT DATE)
            if i+1 < len(lines) and 'STATEMENT' in lines[i+1].upper():
                # Columnar format - value is 5 lines after header
                if i+5 < len(lines):
                    val = lines[i+5].strip()
                    if re.match(r'^\d{6,10}[A-Z]\d{2,4}$', val):
                        return val
    
    # Pattern 2: After "INVOICE NO." header with value on next lines
    for i, line in enumerate(lines):
        if 'INVOICE NO' in line.upper():
            # Check next few lines for the invoice number
            for j in range(i+1, min(i+8, len(lines))):
                val = lines[j].strip()
                # Format: digits + letter + digits (e.g., 8249066T300)
                if re.match(r'^\d{6,10}[A-Z]\d{2,4}$', val):
                    return val
    
    # Pattern 3: Inline format
    match = re.search(r'INVOICE\s*NO\.?\s*[:\s]*(\d{6,10}[A-Z]\d{2,4})', _normalize_text(text), re.I)
    if match:
        return match.group(1)
    
    return None

VENDOR_INVOICES['Waste Connections'] = {
    'format': 'NNNNNNNXDDD',
    'examples': ['8249066T300', '177355066U037', '14281304W319'],
    'extract': _extract_waste_connections_invoice
}


def _extract_republic_services_invoice(text: str) -> Optional[str]:
    """Format: DDDD-NNNNNNNNN (division-sequence)
    Examples: 0176-007823583, 0509-008547612
    """
    # Direct pattern match
    match = re.search(r'(\d{4}-\d{9})', text)
    if match:
        return match.group(1)
    
    # After "Invoice Number" header
    lines = _split_lines(text)
    for i, line in enumerate(lines):
        if 'Invoice Number' in line:
            for j in range(i, min(i+5, len(lines))):
                match = re.search(r'(\d{4}-\d{9})', lines[j])
                if match:
                    return match.group(1)
    
    return None

VENDOR_INVOICES['Republic Services'] = {
    'format': 'DDDD-NNNNNNNNN',
    'examples': ['0176-007823583', '0509-008547612', '0695-007821543'],
    'extract': _extract_republic_services_invoice
}


def _extract_waste_management_invoice(text: str) -> Optional[str]:
    """Format: 10-digit numeric OR NNNNNNN-NNNN-N format (Solutions)
    Examples: 1003677678, 0035886-1015-8
    
    OCR shows: INVOICE NUMBER:\n<value>
    """
    # Filter misdetected vendors
    misdetects = [
        'WIN WASTE', 'WIN INNOVATIONS', 'WEST CENTRAL', 'UNITED STATES DISPOSAL', 
        "STEVE'S SANITATION", 'HEARTLAND WM', 'BLUE COMPACTOR'
    ]
    if any(x in text.upper() for x in misdetects):
        return None
    
    lines = _split_lines(text)
    
    # Pattern 1: WM Solutions columnar format - "Invoice Number" header with value 4 lines later
    for i, line in enumerate(lines):
        if line.strip() == 'Invoice Number':
            # Columnar format - value is ~4 lines after header
            for j in range(i+3, min(i+6, len(lines))):
                val = lines[j].strip()
                # Format: NNNNNNN-NNNN-N
                if re.match(r'^\d{7}-\d{4}-\d$', val):
                    return val
    
    # Pattern 2: After "INVOICE NUMBER:" header (standard WM format)
    for i, line in enumerate(lines):
        if 'INVOICE NUMBER' in line.upper():
            # Check same line for 10-digit
            match = re.search(r'INVOICE\s*NUMBER:?\s*(\d{10})', line, re.I)
            if match:
                return match.group(1)
            # Check next lines for 10-digit
            for j in range(i+1, min(i+5, len(lines))):
                val = lines[j].strip()
                if re.match(r'^\d{10}$', val):
                    return val
    
    # Pattern 3: Direct search for 10-digit in invoice context
    match = re.search(r'Invoice\s*(?:Number|#|No\.?)?:?\s*(\d{10})', _normalize_text(text), re.I)
    if match:
        return match.group(1)
    
    return None

VENDOR_INVOICES['Waste Management'] = {
    'format': 'NNNNNNNNNN',
    'examples': ['1003677678', '1003654321', '1003698745'],
    'extract': _extract_waste_management_invoice
}


def _extract_gfl_invoice(text: str) -> Optional[str]:
    """Format: Prefix + 10 digits (UK0000449634) or just 10 digits
    Examples: UK0000449634, AS0000412567, 0070626851, U10000259821
    """
    # Filter misdetected vendors
    if 'WG WASTE' in text.upper():
        return None
    
    lines = _split_lines(text)
    
    # Pattern 1: "INVOICE NUMBER:" format (10 digits)
    match = re.search(r'INVOICE\s*NUMBER:\s*(\d{10})', text, re.I)
    if match:
        return match.group(1)
    
    # Pattern 2: GFL columnar format - INVOICE #: header with value 4-5 lines later
    for i, line in enumerate(lines):
        if line.strip() == 'INVOICE #:':
            # Check lines 4-6 after header for invoice number
            for j in range(i+4, min(i+7, len(lines))):
                val = lines[j].strip()
                # U prefix + 10-11 digits OR UK/AS prefix + 10 digits
                if re.match(r'^[A-Z]{1,2}\d{10,11}$', val):
                    return val
    
    # Pattern 3: After "INVOICE #:" header (inline or next line)
    for i, line in enumerate(lines):
        if 'INVOICE #' in line.upper() or 'INVOICE#' in line.upper():
            # Check same line
            match = re.search(r'INVOICE\s*#:?\s*([A-Z]{0,2}\d{8,11})', line, re.I)
            if match:
                return match.group(1)
            # Check next lines
            for j in range(i+1, min(i+5, len(lines))):
                val = lines[j].strip()
                if re.match(r'^[A-Z]{0,2}\d{8,11}$', val):
                    return val
    
    # Pattern 4: Direct pattern match (prefix + digits)
    match = re.search(r'\b([A-Z]{2}\d{10})\b', text)
    if match:
        return match.group(1)
    
    return None

VENDOR_INVOICES['GFL'] = {
    'format': 'XXNNNNNNNNNN',
    'examples': ['UK0000449634', 'AS0000412567', 'KW0000398765'],
    'extract': _extract_gfl_invoice
}


# ============================================================
# TIER 2: MEDIUM VOLUME VENDORS (1,000-2,000 invoices)
# ============================================================

def _extract_rumpke_invoice(text: str) -> Optional[str]:
    """Format: 7-digit numeric
    Examples: 3042988, 3041567
    
    OCR shows: Invoice #: <value>
    """
    # Pattern 1: After "Invoice #:" label
    match = re.search(r'Invoice\s*#:?\s*(\d{7})', text, re.I)
    if match:
        return match.group(1)
    
    lines = _split_lines(text)
    for i, line in enumerate(lines):
        if 'Invoice #' in line:
            for j in range(i, min(i+5, len(lines))):
                val = lines[j].strip()
                if re.match(r'^\d{7}$', val):
                    return val
    
    return None

VENDOR_INVOICES['Rumpke'] = {
    'format': 'NNNNNNN',
    'examples': ['3042988', '3041567', '3043215'],
    'extract': _extract_rumpke_invoice
}


def _extract_waste_pro_invoice(text: str) -> Optional[str]:
    """Format: 10-digit numeric with leading zeros OR 9-digit OR 5-digit
    Examples: 0002377717, 0002341935, 0001778219, 244412588, 42960
    
    OCR shows columnar format:
    Account Number:
    Invoice Number:
    Invoice Date:
    <account_value>
    <invoice_value>
    ...
    
    Some formats show: Account # Invoice #: combined on one line with values below
    """
    if 'Recology' in text:
        return None
    
    # Filter payment receipts (not invoices)
    if 'PAYMENT RECEIPT' in text.upper():
        return None
    
    lines = _split_lines(text)
    
    # Pattern 1: 9-10 digit at line 6 (some Waste Pro formats)
    if len(lines) > 6:
        val = lines[6].strip()
        if re.match(r'^\d{9,10}$', val):
            return val
    
    # Pattern 2: Combined account/invoice format "NNNN/NNNNN" at line 14
    for i, line in enumerate(lines):
        if 'Account # Invoice #' in line:
            # Check lines below for combined format
            for j in range(i+1, min(i+10, len(lines))):
                val = lines[j].strip()
                # Format: account/invoice (e.g., 2446/42960)
                match = re.match(r'^\d+/(\d{5,6})$', val)
                if match:
                    return match.group(1)
    
    # Pattern 3: Look for "Invoice Number:" or "Invoice #:" and get value
    for i, line in enumerate(lines):
        if 'Invoice Number' in line or 'Invoice #' in line:
            # Check same line for inline format
            match = re.search(r'Invoice\s*(?:Number|#):?\s*(\d{9,10})', line, re.I)
            if match:
                return match.group(1)
            
            # Check if this is columnar header (has value several lines below)
            for j in range(i+1, min(i+8, len(lines))):
                val = lines[j].strip()
                if re.match(r'^\d{9,10}$', val):
                    return val
    
    # Pattern 4: Direct pattern after label
    match = re.search(r'Invoice\s*(?:Number|#|No\.?)?:?\s*(\d{10})', _normalize_text(text), re.I)
    if match:
        return match.group(1)
    
    return None

VENDOR_INVOICES['Waste Pro'] = {
    'format': 'NNNNNNNNNN',
    'examples': ['0002377717', '0002341935', '0002356789'],
    'extract': _extract_waste_pro_invoice
}


def _extract_casella_invoice(text: str) -> Optional[str]:
    """Format: 7-digit numeric OR YYMMDDKNNNN format
    Examples: 5538229, 5536123, 251027K1874, 5213281
    
    Multiple OCR formats:
    1. Columnar: Invoice # header with value 4-5 lines later
    2. Inline: INVOICE # 5213281
    """
    lines = _split_lines(text)
    
    # Pattern 1: Inline format "INVOICE # NNNNNNN"
    match = re.search(r'INVOICE\s*#\s*(\d{7})', _normalize_text(text), re.I)
    if match:
        return match.group(1)
    
    # Pattern 2: Columnar format - find Invoice # header and get value 4-5 lines later
    for i, line in enumerate(lines):
        if line.strip() == 'Invoice #':
            # Check 4-6 lines later for invoice number
            for j in range(i+4, min(i+7, len(lines))):
                val = lines[j].strip()
                # 7-digit numeric OR YYMMDD + K + digits format
                if re.match(r'^\d{7}$', val):
                    return val
                if re.match(r'^\d{6}[A-Z]\d{3,4}$', val):
                    return val
    
    # Pattern 3: After "Invoice #" header (inline on same line)
    for i, line in enumerate(lines):
        if 'Invoice #' in line or 'Invoice#' in line:
            match = re.search(r'Invoice\s*#:?\s*(\d{7})', line, re.I)
            if match:
                return match.group(1)
            # Also check for YYMMDD+K format
            match = re.search(r'Invoice\s*#:?\s*(\d{6}[A-Z]\d{3,4})', line, re.I)
            if match:
                return match.group(1)
    
    return None

VENDOR_INVOICES['Casella'] = {
    'format': 'NNNNNNN',
    'examples': ['5538229', '5536123', '5534567'],
    'extract': _extract_casella_invoice
}


def _extract_meridian_waste_invoice(text: str) -> Optional[str]:
    """Format: 7-digit numeric
    Examples: 6912577, 6910234
    
    OCR shows: Invoice #\n<value>
    """
    lines = _split_lines(text)
    
    for i, line in enumerate(lines):
        if 'Invoice #' in line:
            # Check same line
            match = re.search(r'Invoice\s*#:?\s*(\d{7})', line, re.I)
            if match:
                return match.group(1)
            # Check next lines
            for j in range(i+1, min(i+5, len(lines))):
                val = lines[j].strip()
                if re.match(r'^\d{7}$', val):
                    return val
    
    return None

VENDOR_INVOICES['Meridian Waste'] = {
    'format': 'NNNNNNN',
    'examples': ['6912577', '6910234', '6908765'],
    'extract': _extract_meridian_waste_invoice
}


def _extract_athens_services_invoice(text: str) -> Optional[str]:
    """Format: 8-digit numeric
    Examples: 20284083, 20281567
    
    OCR shows: INVOICE NUMBER\n<value>
    """
    lines = _split_lines(text)
    
    for i, line in enumerate(lines):
        if 'INVOICE NUMBER' in line.upper():
            # Check next lines
            for j in range(i+1, min(i+5, len(lines))):
                val = lines[j].strip()
                if re.match(r'^\d{8}$', val):
                    return val
    
    # Direct pattern
    match = re.search(r'Invoice\s*Number:?\s*(\d{8})', text, re.I)
    if match:
        return match.group(1)
    
    return None

VENDOR_INVOICES['Athens Services'] = {
    'format': 'NNNNNNNN',
    'examples': ['20284083', '20281567', '20279854'],
    'extract': _extract_athens_services_invoice
}


def _extract_robinson_waste_invoice(text: str) -> Optional[str]:
    """Format: 10-digit with leading zeros
    Examples: 0000363705, 0000361234
    
    OCR shows: INVOICE NO.\n<value>
    """
    lines = _split_lines(text)
    
    for i, line in enumerate(lines):
        if 'INVOICE NO' in line.upper():
            # Check next lines
            for j in range(i+1, min(i+5, len(lines))):
                val = lines[j].strip()
                if re.match(r'^\d{10}$', val):
                    return val
    
    return None

VENDOR_INVOICES['Robinson Waste'] = {
    'format': 'NNNNNNNNNN',
    'examples': ['0000363705', '0000361234', '0000359876'],
    'extract': _extract_robinson_waste_invoice
}


def _extract_lightning_disposal_invoice(text: str) -> Optional[str]:
    """Format: 10-digit with leading zeros
    Examples: 0000857784, 0000856321
    
    OCR shows: INVOICE NO.\n<value>
    """
    lines = _split_lines(text)
    
    for i, line in enumerate(lines):
        if 'INVOICE NO' in line.upper():
            # Check next lines
            for j in range(i+1, min(i+5, len(lines))):
                val = lines[j].strip()
                if re.match(r'^\d{10}$', val):
                    return val
    
    return None

VENDOR_INVOICES['Lightning Disposal'] = {
    'format': 'NNNNNNNNNN',
    'examples': ['0000857784', '0000856321', '0000854567'],
    'extract': _extract_lightning_disposal_invoice
}


def _extract_all_waste_invoice(text: str) -> Optional[str]:
    """Format: 6-digit numeric
    Examples: 425482, 423567
    
    OCR shows: Invoice #\n<value> or Invoice # <value>
    Note: Some documents are reminder notices without invoice numbers.
    """
    lines = _split_lines(text)
    
    # Pattern 1: After "Invoice #" header
    for i, line in enumerate(lines):
        if 'Invoice #' in line or 'Invoice#' in line:
            # Check same line
            match = re.search(r'Invoice\s*#:?\s*(\d{6})', line, re.I)
            if match:
                return match.group(1)
            # Check next lines
            for j in range(i+1, min(i+5, len(lines))):
                val = lines[j].strip()
                if re.match(r'^\d{6}$', val):
                    return val
    
    # Pattern 2: Direct pattern after label
    match = re.search(r'Invoice\s*#:?\s*(\d{6})', _normalize_text(text), re.I)
    if match:
        return match.group(1)
    
    return None

VENDOR_INVOICES['All Waste'] = {
    'format': 'NNNNNN',
    'examples': ['425482', '423567', '421890'],
    'extract': _extract_all_waste_invoice
}


def _extract_granger_waste_invoice(text: str) -> Optional[str]:
    """Format: 8-digit numeric
    Examples: 29584359, 29582456
    
    OCR shows: Invoice Number: <value>
    """
    match = re.search(r'Invoice\s*Number:?\s*(\d{8})', text, re.I)
    if match:
        return match.group(1)
    
    lines = _split_lines(text)
    for i, line in enumerate(lines):
        if 'Invoice Number' in line:
            for j in range(i, min(i+5, len(lines))):
                val = lines[j].strip()
                if re.match(r'^\d{8}$', val):
                    return val
    
    return None

VENDOR_INVOICES['Granger Waste'] = {
    'format': 'NNNNNNNN',
    'examples': ['29584359', '29582456', '29580123'],
    'extract': _extract_granger_waste_invoice
}


# ============================================================
# TIER 3: LOWER VOLUME VENDORS
# ============================================================

def _extract_coastal_waste_invoice(text: str) -> Optional[str]:
    """Format: WW/LC/SW + 10 digits OR Work Order # 6-digit
    Examples: WW0001596777, LC0000332323, SW0001139600, 362016
    
    Multiple OCR formats:
    1. Columnar with WW/LC/SW prefix at line 11-12
    2. Work Order # with value on next line
    """
    lines = _split_lines(text)
    
    # Pattern 1: WW or LC or SW prefix + digits in first 20 lines
    for i, line in enumerate(lines[:20]):
        val = line.strip()
        if re.match(r'^(WW|LC|SW)\d{10}$', val):
            return val
    
    # Pattern 2: Work Order # on line, value on next line
    for i, line in enumerate(lines[:15]):
        if 'Work Order #' in line or 'Work Order#' in line:
            # Check next line for 6-digit number
            if i + 1 < len(lines):
                val = lines[i+1].strip()
                if re.match(r'^\d{6}$', val):
                    return val
            # Check same line
            match = re.search(r'Work\s*Order\s*#:?\s*(\d{6})', line, re.I)
            if match:
                return match.group(1)
    
    # Pattern 3: INVOICE NO. inline format
    match = re.search(r'INVOICE\s*NO\.?\s*(\d{9,10})', _normalize_text(text), re.I)
    if match:
        return match.group(1)
    
    # Pattern 4: Check for Invoice header columnar and get WW/LC/SW value
    for i, line in enumerate(lines):
        if line.strip() == 'Invoice':
            for j in range(i+5, min(i+10, len(lines))):
                val = lines[j].strip()
                if re.match(r'^(WW|LC|SW)\d{10}$', val):
                    return val
    
    return None

VENDOR_INVOICES['Coastal Waste'] = {
    'format': 'NNNNNNN(N)',
    'examples': ['362016', '1234567', '12345678'],
    'extract': _extract_coastal_waste_invoice
}


def _extract_county_waste_invoice(text: str) -> Optional[str]:
    """Format: Various formats - many use NavuSoft
    """
    # Check for County Hauling misdetects
    if 'NOBLE COUNTY' in text.upper() or 'LAKE COUNTY' in text.upper():
        return None
    
    # NavuSoft format
    result = _extract_navusoft_invoice(text, (6, 8))
    if result:
        return result
    
    # Standard Invoice # format
    match = re.search(r'Invoice\s*#:?\s*(\d{6,10})', text, re.I)
    if match:
        return match.group(1)
    
    return None

VENDOR_INVOICES['County Waste'] = {
    'format': 'NNNNNN-NNNNNNNNNN',
    'examples': ['123456', '12345678', '1234567890'],
    'extract': _extract_county_waste_invoice
}


def _extract_universal_waste_invoice(text: str) -> Optional[str]:
    """Format: 10-digit numeric
    Examples: 0004263172, 0004083456
    
    OCR shows columnar format:
    Customer Number:
    Invoice Number:
    Invoice Date:
    P.O. Number:
    Page: 1
    <customer_value>
    <invoice_value>  <- ~5 lines after Invoice Number header
    """
    lines = _split_lines(text)
    
    # Pattern 1: Find Invoice Number header and get value several lines later
    for i, line in enumerate(lines):
        if 'Invoice Number' in line:
            # Check for columnar format - value is several lines after header
            for j in range(i+1, min(i+10, len(lines))):
                val = lines[j].strip()
                if re.match(r'^\d{10}$', val):
                    return val
    
    # Pattern 2: Direct pattern
    match = re.search(r'Invoice\s*Number:?\s*(\d{10})', _normalize_text(text), re.I)
    if match:
        return match.group(1)
    
    return None

VENDOR_INVOICES['Universal Waste'] = {
    'format': 'NNNNNN(N)',
    'examples': ['273586', '274126', '261300'],
    'extract': _extract_universal_waste_invoice
}


def _extract_green_guys_invoice(text: str) -> Optional[str]:
    """Format: INVOICE #NNNN or INVOICE #NNNNN
    Examples: 4204, 20044
    
    OCR shows: INVOICE #<number>
    """
    match = re.search(r'INVOICE\s*#\s*(\d{4,6})', text, re.I)
    if match:
        return match.group(1)
    
    return None

VENDOR_INVOICES['Green Guys'] = {
    'format': 'NNNN-NNNNN',
    'examples': ['4204', '20044', '19876'],
    'extract': _extract_green_guys_invoice
}


def _extract_cockey_invoice(text: str) -> Optional[str]:
    """Format: 7-digit numeric (NavuSoft)
    Examples: 3099926, 3089456
    
    OCR shows invoice number at line 1, before header block.
    """
    lines = _split_lines(text)
    
    # Pattern 1: NavuSoft format - invoice number at line 1
    if len(lines) > 1:
        val = lines[1].strip()
        if re.match(r'^\d{7}$', val):
            return val
    
    # Pattern 2: After INVOICE # header
    for i, line in enumerate(lines):
        if 'INVOICE #' in line.upper():
            for j in range(i+1, min(i+8, len(lines))):
                val = lines[j].strip()
                if re.match(r'^\d{6,7}$', val):
                    return val
    
    return None

VENDOR_INVOICES["Cockey's Enterprises"] = {
    'format': 'NNNNNN',
    'examples': ['123456', '654321'],
    'extract': _extract_cockey_invoice
}


def _extract_american_disposal_invoice(text: str) -> Optional[str]:
    """Format: 9-digit numeric OR Waste Connections subsidiary format
    Examples: 540510573, 14281304W319
    
    OCR shows: Invoice 540510573 at line 0
    """
    # Pattern 1: Invoice + 9 digits at line 0
    match = re.search(r'Invoice\s+(\d{9})', _normalize_text(text), re.I)
    if match:
        return match.group(1)
    
    # Pattern 2: Try Waste Connections pattern (subsidiary)
    wc_result = _extract_waste_connections_invoice(text)
    if wc_result:
        return wc_result
    
    return None

VENDOR_INVOICES['American Disposal'] = {
    'format': 'NNNNNNNNN',
    'examples': ['540510573', '540456789'],
    'extract': _extract_american_disposal_invoice
}


def _extract_patriot_waste_invoice(text: str) -> Optional[str]:
    """Format: 6-8 digit numeric
    """
    if 'PATRIOT' not in text.upper():
        return None
    
    match = re.search(r'Invoice\s*#?:?\s*(\d{6,8})', text, re.I)
    if match:
        return match.group(1)
    
    return _extract_navusoft_invoice(text, (6, 8))

VENDOR_INVOICES['Patriot Waste'] = {
    'format': 'NNNNNN-NNNNNNNN',
    'examples': ['123456', '12345678'],
    'extract': _extract_patriot_waste_invoice
}


def _extract_basin_disposal_invoice(text: str) -> Optional[str]:
    """Format: 6-8 digit numeric
    """
    match = re.search(r'Invoice\s*#?:?\s*(\d{6,8})', text, re.I)
    if match:
        return match.group(1)
    
    return None

VENDOR_INVOICES['Basin Disposal'] = {
    'format': 'NNNNNN-NNNNNNNN',
    'examples': ['123456', '12345678'],
    'extract': _extract_basin_disposal_invoice
}


def _extract_texas_disposal_invoice(text: str) -> Optional[str]:
    """Format: 7-digit numeric
    """
    match = re.search(r'Invoice\s*#?:?\s*(\d{7})', text, re.I)
    if match:
        return match.group(1)
    
    return None

VENDOR_INVOICES['Texas Disposal'] = {
    'format': 'NNNNNNN',
    'examples': ['1234567', '7654321'],
    'extract': _extract_texas_disposal_invoice
}


def _extract_kimble_invoice(text: str) -> Optional[str]:
    """Format: 6-8 digit numeric
    """
    match = re.search(r'Invoice\s*(?:Number|#|No\.?)?:?\s*(\d{6,8})', text, re.I)
    if match:
        return match.group(1)
    
    return None

VENDOR_INVOICES['Kimble'] = {
    'format': 'NNNNNN-NNNNNNNN',
    'examples': ['123456', '12345678'],
    'extract': _extract_kimble_invoice
}


def _extract_apex_waste_invoice(text: str) -> Optional[str]:
    """Format: 6-8 digit numeric
    """
    match = re.search(r'Invoice\s*#?:?\s*(\d{6,8})', text, re.I)
    if match:
        return match.group(1)
    
    return _extract_navusoft_invoice(text, (6, 8))

VENDOR_INVOICES['Apex Waste'] = {
    'format': 'NNNNNN-NNNNNNNN',
    'examples': ['123456', '12345678'],
    'extract': _extract_apex_waste_invoice
}


def _extract_metalpro_invoice(text: str) -> Optional[str]:
    """Format: 5-6 digit numeric
    """
    if 'METALPRO' not in text.upper():
        return None
    
    match = re.search(r'Invoice\s*(?:Number|#|No\.?)?:?\s*(\d{5,6})', text, re.I)
    if match:
        return match.group(1)
    
    return None

VENDOR_INVOICES['MetalPro'] = {
    'format': 'NNNNN-NNNNNN',
    'examples': ['12345', '123456'],
    'extract': _extract_metalpro_invoice
}


def _extract_ace_recycling_invoice(text: str) -> Optional[str]:
    """Format: 5-6 digit numeric
    """
    match = re.search(r'Invoice\s*#?:?\s*(\d{5,6})', text, re.I)
    if match:
        return match.group(1)
    
    return None

VENDOR_INVOICES['Ace Recycling'] = {
    'format': 'NNNNN-NNNNNN',
    'examples': ['12345', '123456'],
    'extract': _extract_ace_recycling_invoice
}


def _extract_mark_dunning_invoice(text: str) -> Optional[str]:
    """Format: 6-8 digit numeric
    """
    match = re.search(r'Invoice\s*#?:?\s*(\d{6,8})', text, re.I)
    if match:
        return match.group(1)
    
    lines = _split_lines(text)
    for i, line in enumerate(lines):
        if 'INVOICE' in line.upper():
            for j in range(i+1, min(i+5, len(lines))):
                val = lines[j].strip()
                if re.match(r'^\d{6,8}$', val):
                    return val
    
    return None

VENDOR_INVOICES['Mark Dunning'] = {
    'format': 'NNNNNN-NNNNNNNN',
    'examples': ['1373624', '1347666'],
    'extract': _extract_mark_dunning_invoice
}


def _extract_detroit_disposal_invoice(text: str) -> Optional[str]:
    """Format: 6-8 digit numeric
    """
    match = re.search(r'Invoice\s*(?:Number|#|No\.?)?:?\s*(\d{6,8})', text, re.I)
    if match:
        return match.group(1)
    
    return None

VENDOR_INVOICES['Detroit Disposal'] = {
    'format': 'NNNNNN-NNNNNNNN',
    'examples': ['307400', '307201'],
    'extract': _extract_detroit_disposal_invoice
}


def _extract_jp_mascaro_invoice(text: str) -> Optional[str]:
    """Format: 10-digit numeric
    Examples: 0000727716
    
    OCR shows:
    Line 7: 0000727716 (invoice number)
    Line 9: INVOICE NO. (header)
    """
    lines = _split_lines(text)
    
    # Pattern 1: 10-digit at line 7
    if len(lines) > 7:
        val = lines[7].strip()
        if re.match(r'^\d{10}$', val):
            return val
    
    # Pattern 2: Find INVOICE NO. header and look BEFORE
    for i, line in enumerate(lines):
        if line.strip() == 'INVOICE NO.':
            for j in range(max(0, i-3), i):
                val = lines[j].strip()
                if re.match(r'^\d{10}$', val):
                    return val
    
    # Pattern 3: Direct pattern
    match = re.search(r'Invoice\s*(?:Number|#|No\.?)?:?\s*(\d{10})', text, re.I)
    if match:
        return match.group(1)
    
    return None

VENDOR_INVOICES['JP Mascaro'] = {
    'format': 'NNNNNNNNNN',
    'examples': ['0000727716', '0000654321'],
    'extract': _extract_jp_mascaro_invoice
}


def _extract_american_recycling_invoice(text: str) -> Optional[str]:
    """Format: Ticket # with alphanumeric (2-3 letters + 7-8 digits)
    Examples: GK50852093, GKE0724596, GJN0948214
    
    OCR shows: Ticket # GKE0724596
    """
    # Pattern 1: Ticket # format with 2-3 letters + 7-8 digits
    match = re.search(r'Ticket\s*#\s*([A-Z]{2,3}\d{7,8})', _normalize_text(text), re.I)
    if match:
        return match.group(1)
    
    # Pattern 2: Direct pattern at line 1
    lines = _split_lines(text)
    if len(lines) > 1:
        match = re.match(r'^Ticket\s*#\s*([A-Z]{2,3}\d{7,8})$', lines[1].strip(), re.I)
        if match:
            return match.group(1)
    
    # Pattern 3: Any 2-3 letter + 7-8 digit pattern
    match = re.search(r'\b([A-Z]{2,3}\d{7,8})\b', text)
    if match:
        return match.group(1)
    
    return None

VENDOR_INVOICES['American Recycling'] = {
    'format': 'XX(X)NNNNNNNN',
    'examples': ['GK50852093', 'GKE0724596', 'GJN0948214'],
    'extract': _extract_american_recycling_invoice
}


# ============================================================
# ADDITIONAL VENDORS (Added December 2024)
# ============================================================

def _extract_active_waste_invoice(text: str) -> Optional[str]:
    """Format: 6-digit numeric (NavuSoft format)
    Examples: 722787, 715432
    
    OCR shows invoice number at line 0, before header block.
    """
    lines = _split_lines(text)
    
    # Pattern 1: NavuSoft format - invoice at line 0
    if len(lines) > 0:
        val = lines[0].strip()
        if re.match(r'^\d{6}$', val):
            return val
    
    # Pattern 2: After INVOICE # header (columnar format)
    for i, line in enumerate(lines):
        if line.strip() == 'INVOICE #':
            if i+5 < len(lines):
                val = lines[i+5].strip()
                if re.match(r'^\d{6}$', val):
                    return val
    
    return None

VENDOR_INVOICES['Active Waste'] = {
    'format': 'NNNNNN',
    'examples': ['722787', '715432', '709876'],
    'extract': _extract_active_waste_invoice
}


def _extract_priority_waste_invoice(text: str) -> Optional[str]:
    """Format: INV + 7 digits
    Examples: INV1359275, INV1345678
    
    OCR shows: Invoice # INV1359275
    """
    # Direct pattern match
    match = re.search(r'Invoice\s*#?\s*(INV\d{7})', _normalize_text(text), re.I)
    if match:
        return match.group(1)
    
    return None

VENDOR_INVOICES['Priority Waste'] = {
    'format': 'INVNNNNNNN',
    'examples': ['INV1359275', 'INV1345678', 'INV1234567'],
    'extract': _extract_priority_waste_invoice
}


def _extract_aspen_waste_invoice(text: str) -> Optional[str]:
    """Format: Ref #: SN NNNNNN-MMDDYY
    Examples: S4 738595-103125
    
    OCR shows: Ref #: S4 738595-103125
    """
    # Pattern: Ref # format
    match = re.search(r'Ref\s*#?:?\s*([A-Z]\d[\s-]*\d+-\d+)', _normalize_text(text), re.I)
    if match:
        return match.group(1).replace(' ', '')
    
    # Alternative: Statement number format
    match = re.search(r'Statement\s*(?:Date|No\.?|#)?:?\s*\d+/\d+/\d+\s*Ref\s*#?:?\s*([^\s]+)', _normalize_text(text), re.I)
    if match:
        return match.group(1)
    
    return None

VENDOR_INVOICES['Aspen Waste'] = {
    'format': 'SN-NNNNNN-MMDDYY',
    'examples': ['S4738595-103125', 'S4-738595-103125'],
    'extract': _extract_aspen_waste_invoice
}


def _extract_win_waste_invoice(text: str) -> Optional[str]:
    """Format: NN-NNNNNNNNNN (e.g., 22-0001874506, 30-0001459906)
    WIN Waste Innovations format
    """
    # Pattern: INVOICE NN-NNNNNNNNNN
    match = re.search(r'INVOICE\s+(\d{2}-\d{10})', _normalize_text(text), re.I)
    if match:
        return match.group(1)
    
    return None

VENDOR_INVOICES['WIN Waste'] = {
    'format': 'NN-NNNNNNNNNN',
    'examples': ['22-0001874506', '30-0001459906'],
    'extract': _extract_win_waste_invoice
}

# Also register as "Win Waste" (different capitalization)
VENDOR_INVOICES['Win Waste'] = VENDOR_INVOICES['WIN Waste']


def _extract_west_central_invoice(text: str) -> Optional[str]:
    """Format: 8-digit numeric
    West Central Sanitation columnar format
    """
    if 'WEST CENTRAL' not in text.upper():
        return None
    
    lines = _split_lines(text)
    
    # Columnar format: Invoice Number header with value 6 lines later
    for i, line in enumerate(lines):
        if line.strip() == 'Invoice Number':
            for j in range(i+5, min(i+8, len(lines))):
                val = lines[j].strip()
                if re.match(r'^\d{8}$', val):
                    return val
    
    return None

VENDOR_INVOICES['West Central Sanitation'] = {
    'format': 'NNNNNNNN',
    'examples': ['13617235', '13598765'],
    'extract': _extract_west_central_invoice
}


def _extract_lrs_invoice(text: str) -> Optional[str]:
    """Format: 2 letters + 5-7 digits
    Examples: AM136536, UA43738, G1116435, MH6229184
    
    OCR shows columnar format with Invoice No header
    """
    lines = _split_lines(text)
    
    # Pattern 1: Columnar format - find Invoice No header
    for i, line in enumerate(lines[:12]):
        if line.strip() == 'Invoice No':
            # Check lines 4-8 after header for alphanumeric invoice
            for j in range(i+3, min(i+8, len(lines))):
                val = lines[j].strip()
                # Various prefixes: AM, UA, G, MH, etc.
                if re.match(r'^[A-Z]{1,2}\d{5,7}$', val):
                    return val
    
    # Pattern 2: Direct pattern match - any 1-2 letter prefix + 5-7 digits
    match = re.search(r'\b([A-Z]{1,2}\d{5,7})\b', _normalize_text(text))
    if match:
        return match.group(1)
    
    return None

VENDOR_INVOICES['LRS'] = {
    'format': 'XXNNNNNN',
    'examples': ['AM136536', 'AM145678', 'AM123456'],
    'extract': _extract_lrs_invoice
}


def _extract_standard_waste_invoice(text: str) -> Optional[str]:
    """Format: 6-digit numeric
    Examples: 552592, 550576
    
    OCR shows: Invoice # 552592 (inline format)
    """
    # Pattern 1: Inline format "Invoice # NNNNNN"
    match = re.search(r'Invoice\s*#\s*(\d{6})', _normalize_text(text), re.I)
    if match:
        return match.group(1)
    
    lines = _split_lines(text)
    
    # Pattern 2: After Invoice # header
    for i, line in enumerate(lines):
        if 'Invoice #' in line or 'Invoice#' in line or 'INVOICE #' in line:
            match = re.search(r'Invoice\s*#:?\s*(\d{6})', line, re.I)
            if match:
                return match.group(1)
            for j in range(i+1, min(i+5, len(lines))):
                val = lines[j].strip()
                if re.match(r'^\d{6}$', val):
                    return val
    
    return None

VENDOR_INVOICES['Standard Waste'] = {
    'format': 'NNNNNN',
    'examples': ['552592', '550576', '548123'],
    'extract': _extract_standard_waste_invoice
}


def _extract_smarttrash_invoice(text: str) -> Optional[str]:
    """Format: INV + 6 digits
    Examples: INV027437, INV025678
    
    OCR shows: Invoice No.: INV027437
    """
    match = re.search(r'Invoice\s*No\.?:?\s*(INV\d{6})', _normalize_text(text), re.I)
    if match:
        return match.group(1)
    
    return None

VENDOR_INVOICES['SmartTrash'] = {
    'format': 'INVNNNNNN',
    'examples': ['INV027437', 'INV025678', 'INV023456'],
    'extract': _extract_smarttrash_invoice
}


def _extract_best_cleaner_invoice(text: str) -> Optional[str]:
    """Format: 12-digit numeric
    Examples: 621620359356, 621620355746
    
    OCR shows ID at line 3, may or may not have ID#: prefix
    Some documents are payment confirmations without ID.
    """
    lines = _split_lines(text)
    
    # Pattern 1: ID at line 3 (common format)
    if len(lines) > 3:
        val = lines[3].strip()
        if re.match(r'^\d{12}$', val):
            return val
    
    # Pattern 2: ID#: prefix format
    match = re.search(r'ID#:?\s*(\d{12})', _normalize_text(text), re.I)
    if match:
        return match.group(1)
    
    # Pattern 3: Search first 10 lines for 12-digit number
    for i, line in enumerate(lines[:10]):
        val = line.strip()
        if re.match(r'^\d{12}$', val):
            return val
    
    return None

VENDOR_INVOICES['Best Cleaner'] = {
    'format': 'NNNNNNNNNNNN',
    'examples': ['621620359356', '621620345678'],
    'extract': _extract_best_cleaner_invoice
}


def _extract_alaska_waste_invoice(text: str) -> Optional[str]:
    """Format: NNNNNNNNNSNNN (Waste Connections subsidiary format)
    Examples: 103474701S430
    
    OCR shows columnar format like Waste Connections.
    """
    # Use same pattern as Waste Connections
    return _extract_waste_connections_invoice(text)

VENDOR_INVOICES['Alaska Waste'] = {
    'format': 'NNNNNNNNNSNNN',
    'examples': ['103474701S430', '103456789S430'],
    'extract': _extract_alaska_waste_invoice
}


def _extract_eagle_disposal_invoice(text: str) -> Optional[str]:
    """Format: 12-digit numeric (same format as Best Cleaner)
    Examples: 638730778561, 638730715952
    
    OCR shows ID at line 3 (no prefix)
    Some documents are payment receipts without invoice numbers.
    """
    lines = _split_lines(text)
    
    # Pattern 1: 12-digit at line 3
    if len(lines) > 3:
        val = lines[3].strip()
        if re.match(r'^\d{12}$', val):
            return val
    
    # Pattern 2: Search first 10 lines for 12-digit number
    for i, line in enumerate(lines[:10]):
        val = line.strip()
        if re.match(r'^\d{12}$', val):
            return val
    
    # Pattern 3: Invoice NNNNNN format
    match = re.search(r'Invoice\s+(\d{6})', _normalize_text(text), re.I)
    if match:
        return match.group(1)
    
    return None

VENDOR_INVOICES['Eagle Disposal'] = {
    'format': 'NNNNNN',
    'examples': ['817917', '815678'],
    'extract': _extract_eagle_disposal_invoice
}


def _extract_murreys_disposal_invoice(text: str) -> Optional[str]:
    """Format: Waste Connections subsidiary
    """
    return _extract_waste_connections_invoice(text)

VENDOR_INVOICES['Murreys Disposal'] = {
    'format': 'NNNNNNNNNXNNN',
    'examples': ['123456789X123'],
    'extract': _extract_murreys_disposal_invoice
}


def _extract_papillion_sanitation_invoice(text: str) -> Optional[str]:
    """Format: Various - check for Waste Connections subsidiary pattern
    """
    return _extract_waste_connections_invoice(text)

VENDOR_INVOICES['Papillion Sanitation'] = {
    'format': 'NNNNNNNNNXNNN',
    'examples': ['123456789X123'],
    'extract': _extract_papillion_sanitation_invoice
}


def _extract_capital_waste_invoice(text: str) -> Optional[str]:
    """Format: 7-digit numeric in columnar format
    Examples: 2674727, 71543, 32284843
    
    OCR shows columnar headers with values below:
    AMOUNT
    ACCOUNT
    DATE
    DUE DATE
    <account_number>  <- 7 digits
    ...
    """
    lines = _split_lines(text)
    
    # Pattern 1: Find ACCOUNT header and get 7-digit value 2 lines later
    for i, line in enumerate(lines):
        if line.strip() == 'ACCOUNT':
            # Check 2-4 lines later for 7-digit number
            for j in range(i+2, min(i+5, len(lines))):
                val = lines[j].strip()
                if re.match(r'^\d{7}$', val):
                    return val
    
    # Pattern 2: 5-digit at line 0 (credit memo format)
    if len(lines) > 0:
        val = lines[0].strip()
        if re.match(r'^\d{5}$', val):
            return val
    
    # Pattern 3: WO # (Work Order)
    for i, line in enumerate(lines):
        if line.strip() == 'WO #':
            if i+1 < len(lines):
                val = lines[i+1].strip()
                if re.match(r'^\d{7,8}$', val):
                    return val
    
    # Pattern 4: Standard invoice pattern
    match = re.search(r'Invoice\s*(?:#|No\.?|Number)?:?\s*(\d{5,10})', _normalize_text(text), re.I)
    if match:
        return match.group(1)
    
    return None

VENDOR_INVOICES['Capital Waste'] = {
    'format': 'NNNNN or NNNNNNNN',
    'examples': ['71543', '32284843'],
    'extract': _extract_capital_waste_invoice
}


def _extract_friedman_recycling_invoice(text: str) -> Optional[str]:
    """Format: 6-digit numeric
    Examples: 500314, 492541, 493151
    
    Two OCR columnar formats:
    Format 1 - values BEFORE headers:
      Line 10: invoice number (6-digit)
      Line 13: Invoice Number <- LABEL
    
    Format 2 - values AFTER headers:
      Line 11: Invoice Number <- LABEL
      Line 16: date
      Line 17: invoice number (6-digit)
    """
    lines = _split_lines(text)
    
    # Pattern 1: Find "Invoice Number" header and look BEFORE for value
    for i, line in enumerate(lines):
        if line.strip() == 'Invoice Number':
            # Check 2-4 lines BEFORE the header
            for j in range(max(0, i-4), i):
                val = lines[j].strip()
                if re.match(r'^\d{6}$', val):
                    return val
            # Also check 5-7 lines AFTER (for format 2)
            for j in range(i+5, min(i+8, len(lines))):
                val = lines[j].strip()
                if re.match(r'^\d{6}$', val):
                    return val
    
    # Pattern 2: Look at line 10 directly for 6-digit
    if len(lines) > 10:
        val = lines[10].strip()
        if re.match(r'^\d{6}$', val):
            return val
    
    # Pattern 3: Look at line 17 for format 2
    if len(lines) > 17:
        val = lines[17].strip()
        if re.match(r'^\d{6}$', val):
            return val
    
    # Pattern 4: Search lines 8-20 for 6-digit number
    for i in range(8, min(21, len(lines))):
        val = lines[i].strip()
        if re.match(r'^\d{6}$', val):
            return val
    
    return None

VENDOR_INVOICES['Friedman Recycling'] = {
    'format': 'NNNNNN',
    'examples': ['500314', '498765'],
    'extract': _extract_friedman_recycling_invoice
}


def _extract_navajo_sanitation_invoice(text: str) -> Optional[str]:
    """Format: 12-digit numeric (ID#) OR 6-digit (Invoice)
    Examples: 577170042972, 135678
    
    OCR shows:
    - ID#: 577170044245 (with prefix) OR
    - 12-digit at line 3 (no prefix) OR
    - Invoice 135678 (6-digit)
    """
    lines = _split_lines(text)
    
    # Pattern 1: ID#: prefix with 12-digit
    match = re.search(r'ID#:?\s*(\d{12})', _normalize_text(text), re.I)
    if match:
        return match.group(1)
    
    # Pattern 2: 12-digit at line 3
    if len(lines) > 3:
        val = lines[3].strip()
        if re.match(r'^\d{12}$', val):
            return val
    
    # Pattern 3: Invoice + 6-digit
    match = re.search(r'Invoice\s+(\d{6})\b', _normalize_text(text), re.I)
    if match:
        return match.group(1)
    
    # Pattern 4: Search first 10 lines for 12-digit number
    for i, line in enumerate(lines[:10]):
        val = line.strip()
        if re.match(r'^\d{12}$', val):
            return val
    
    return None

VENDOR_INVOICES['Navajo Sanitation'] = {
    'format': 'NNNNNNNNNNNN',
    'examples': ['577170042972', '577170043456'],
    'extract': _extract_navajo_sanitation_invoice
}


def _extract_waste_zero_invoice(text: str) -> Optional[str]:
    """Format: 10-digit or 13-digit or 8-digit numeric
    Examples: 0005298824, 8551003748931, 0000083808, 78227568
    
    Multiple OCR formats:
    1. INVOICE NO. header with value on next line
    2. Columnar: Invoice/Number split headers
    3. Inline: date + invoice + account on same line
    4. Billing Number format (Recology) - value 5 lines after header
    5. Statement format with inline invoice number
    """
    lines = _split_lines(text)
    
    # Pattern 1: INVOICE NO. header with value on next line
    for i, line in enumerate(lines[:15]):
        if line.strip() == 'INVOICE NO.':
            for j in range(i+2, min(i+5, len(lines))):
                val = lines[j].strip()
                if re.match(r'^\d{10}$', val):
                    return val
    
    # Pattern 2: Columnar - find "Invoice" then "Number" split headers
    for i, line in enumerate(lines[:15]):
        if line.strip() == 'Invoice':
            if i+1 < len(lines) and lines[i+1].strip() == 'Number':
                for j in range(i+8, min(i+12, len(lines))):
                    val = lines[j].strip()
                    if re.match(r'^\d{10}$', val):
                        return val
    
    # Pattern 3: Inline format - "date invoice account" on same line
    for i, line in enumerate(lines[:10]):
        match = re.search(r'\d{1,2}/\d{1,2}/\d{2,4}\s+(\d{13})\s+\d{10}', line)
        if match:
            return match.group(1)
    
    # Pattern 4: Billing Number format (Recology) - value 5 lines after header
    for i, line in enumerate(lines):
        if 'Billing Number:' in line:
            # Value is 4-6 lines later
            for j in range(i+3, min(i+8, len(lines))):
                val = lines[j].strip()
                if re.match(r'^\d{8}$', val):
                    return val
    
    # Pattern 5: Statement format with inline invoice number
    for i, line in enumerate(lines):
        # Look for date + 13-digit invoice pattern
        match = re.search(r'\d{1,2}/\d{1,2}/\d{2}\s+(\d{13})', line)
        if match:
            return match.group(1)
    
    # Pattern 6: Search for standalone 8, 10, or 13 digit numbers
    for i, line in enumerate(lines[:25]):
        val = line.strip()
        if re.match(r'^\d{8}$', val) or re.match(r'^\d{10}$', val) or re.match(r'^\d{13}$', val):
            # Skip dates
            if not re.match(r'^(10|11|12|01|02|03|04|05|06|07|08|09)\d{6,8}$', val):
                return val
    
    return None

VENDOR_INVOICES['Waste Zero'] = {
    'format': 'NNNNNNNN-NNNNNNNNNNNNN',
    'examples': ['0005298824', '78227568', '8551003748931'],
    'extract': _extract_waste_zero_invoice
}


def _extract_novak_sanitary_invoice(text: str) -> Optional[str]:
    """Format: Waste Connections subsidiary format NNNNNNNTNNN
    Examples: 4522169T031
    
    OCR shows:
    Line 7: INVOICE NO.
    Line 8: 4522169T031
    """
    lines = _split_lines(text)
    
    # Pattern 1: INVOICE NO. header with value on next line
    for i, line in enumerate(lines[:15]):
        if line.strip() == 'INVOICE NO.':
            if i+1 < len(lines):
                val = lines[i+1].strip()
                # Waste Connections format: digits + letter + digits
                if re.match(r'^\d{7}[A-Z]\d{3}$', val):
                    return val
    
    # Pattern 2: Use Waste Connections extractor
    result = _extract_waste_connections_invoice(text)
    if result:
        return result
    
    return None

VENDOR_INVOICES['Novak Sanitary'] = {
    'format': 'NNNNNNNXNNN',
    'examples': ['4522169T031', '4512345T031'],
    'extract': _extract_novak_sanitary_invoice
}


def _extract_ecosouth_invoice(text: str) -> Optional[str]:
    """Format: INV + 6 digits OR 9-digit Transaction Number
    Examples: INV169903, 330305014
    
    OCR formats:
    1. Invoice format: INV169903
    2. Payment receipt: Transaction Number 330305014
    """
    lines = _split_lines(text)
    
    # Pattern 1: INV prefix format anywhere in first 15 lines
    for i, line in enumerate(lines[:15]):
        val = line.strip()
        if re.match(r'^INV\d{6}$', val):
            return val
    
    # Pattern 2: Transaction Number for payment receipts
    for i, line in enumerate(lines):
        if 'Transaction Number' in line:
            if i+1 < len(lines):
                val = lines[i+1].strip()
                if re.match(r'^\d{9}$', val):
                    return val
    
    # Pattern 3: Payment Successful [NNNNNNNNN] format
    match = re.search(r'Payment Successful\s*\[(\d{9})\]', _normalize_text(text))
    if match:
        return match.group(1)
    
    # Pattern 4: Direct search for INV format
    match = re.search(r'\b(INV\d{6})\b', _normalize_text(text))
    if match:
        return match.group(1)
    
    return None

VENDOR_INVOICES['EcoSouth'] = {
    'format': 'INVNNNNNN or NNNNNNNNN',
    'examples': ['INV169903', '330305014'],
    'extract': _extract_ecosouth_invoice
}


def _extract_edco_disposal_invoice(text: str) -> Optional[str]:
    """Format: NN-XX NNNNNN (account-based, various letter/digit combos)
    Examples: 56-K4 728368, 37-ER 720221, 25-1A 170459
    
    EDCO uses account number as invoice identifier
    OCR shows: Account Number header, value at line 5
    """
    lines = _split_lines(text)
    
    # Pattern 1: Look at line 5 for account format
    if len(lines) > 5:
        val = lines[5].strip()
        # Format: NN-XX NNNNNN where XX can be letter+digit, digit+letter, or 2 letters
        if re.match(r'^\d{2}-[A-Z0-9]{2}\s+\d{6}$', val):
            return val.replace(' ', '-')
    
    # Pattern 2: After "Account Number" header
    for i, line in enumerate(lines[:10]):
        if 'Account Number' in line:
            for j in range(i+1, min(i+6, len(lines))):
                val = lines[j].strip()
                if re.match(r'^\d{2}-[A-Z0-9]{2}\s+\d{6}$', val):
                    return val.replace(' ', '-')
    
    # Pattern 3: Direct pattern search (flexible middle part)
    match = re.search(r'(\d{2}-[A-Z0-9]{2}[\s-]\d{6})', _normalize_text(text))
    if match:
        return match.group(1).replace(' ', '-')
    
    return None

VENDOR_INVOICES['EDCO Disposal'] = {
    'format': 'NN-XX-NNNNNN',
    'examples': ['56-K4-728368', '37-ER-720221', '25-1A-170459'],
    'extract': _extract_edco_disposal_invoice
}


def _extract_compactor_rentals_invoice(text: str) -> Optional[str]:
    """Format: NNNNNN(NN)-NNNN (hyphenated, 6-8 digits before hyphen)
    Examples: 104565-0039, 3684633-0023, 36846316-0022
    
    OCR shows invoice number around line 17-18
    """
    lines = _split_lines(text)
    
    # Pattern 1: NNNNNN-NNNN or NNNNNNN-NNNN or NNNNNNNN-NNNN format
    for i, line in enumerate(lines[:25]):
        val = line.strip()
        if re.match(r'^\d{6,8}-\d{4}$', val):
            return val
    
    # Pattern 2: Direct search
    match = re.search(r'\b(\d{6,8}-\d{4})\b', _normalize_text(text))
    if match:
        return match.group(1)
    
    return None

VENDOR_INVOICES['Compactor Rentals of America'] = {
    'format': 'NNNNNN(NN)-NNNN',
    'examples': ['104565-0039', '3684633-0023', '36846316-0022'],
    'extract': _extract_compactor_rentals_invoice
}


def _extract_boyas_recycling_invoice(text: str) -> Optional[str]:
    """Format: INV-NNNNNN
    Examples: INV-168186
    
    OCR shows: Invoice Number header at line 17, value at line 22
    """
    lines = _split_lines(text)
    
    # Pattern 1: INV-NNNNNN format in lines 20-25
    for i, line in enumerate(lines[18:28]):
        val = line.strip()
        if re.match(r'^INV-\d{6}$', val):
            return val
    
    # Pattern 2: After Invoice Number header
    for i, line in enumerate(lines):
        if line.strip() == 'Invoice Number':
            for j in range(i+1, min(i+8, len(lines))):
                val = lines[j].strip()
                if re.match(r'^INV-\d{6}$', val):
                    return val
    
    # Pattern 3: Direct pattern search
    match = re.search(r'\b(INV-\d{6})\b', _normalize_text(text))
    if match:
        return match.group(1)
    
    return None

VENDOR_INVOICES['Boyas Recycling'] = {
    'format': 'INV-NNNNNN',
    'examples': ['INV-168186', 'INV-154321'],
    'extract': _extract_boyas_recycling_invoice
}


def _extract_detroit_disposal_invoice(text: str) -> Optional[str]:
    """Format: 6-digit numeric
    Examples: 291416, 307400
    
    OCR columnar format - values appear BEFORE labels:
    Line 12: account value (307400)
    Line 14: invoice value (291416)
    Line 16: Invoice Number label
    """
    lines = _split_lines(text)
    
    # Pattern 1: Find Invoice Number label and look BEFORE
    for i, line in enumerate(lines):
        if line.strip() == 'Invoice Number':
            # Value is 2 lines before
            for j in range(max(0, i-3), i):
                val = lines[j].strip()
                if re.match(r'^\d{6}$', val):
                    return val
    
    # Pattern 2: Look at line 14 directly
    if len(lines) > 14:
        val = lines[14].strip()
        if re.match(r'^\d{6}$', val):
            return val
    
    return None

VENDOR_INVOICES['Detroit Disposal'] = {
    'format': 'NNNNNN',
    'examples': ['291416', '307400'],
    'extract': _extract_detroit_disposal_invoice
}


def _extract_cri_curbside_invoice(text: str) -> Optional[str]:
    """Format: 6-digit numeric
    Examples: 339814, 339737
    
    OCR shows: INVOICE # at line 1 or 2, value at line 7-8
    """
    lines = _split_lines(text)
    
    # Pattern 1: Find INVOICE # or Invoice # header
    for i, line in enumerate(lines[:5]):
        if 'INVOICE #' in line.upper() or line.strip() == 'Invoice #':
            # Value is about 5-7 lines later (skip address which is 5-digit with letters)
            for j in range(i+5, min(i+9, len(lines))):
                val = lines[j].strip()
                # Must be exactly 6 digits (not address like 15600)
                if re.match(r'^\d{6}$', val):
                    return val
    
    # Pattern 2: Look at lines 7-9 for 6-digit number
    for i in range(7, min(10, len(lines))):
        val = lines[i].strip()
        if re.match(r'^\d{6}$', val):
            return val
    
    return None

VENDOR_INVOICES['CRI Curbside'] = {
    'format': 'NNNNNN',
    'examples': ['339814', '335678'],
    'extract': _extract_cri_curbside_invoice
}


def _extract_apex_waste_invoice(text: str) -> Optional[str]:
    """Format: 12-digit numeric
    Examples: 251030099185
    
    OCR shows: Invoice #: at line 14, value at line 17
    """
    lines = _split_lines(text)
    
    # Pattern 1: Find Invoice #: header
    for i, line in enumerate(lines):
        if line.strip() == 'Invoice #:':
            # Value is about 3 lines later
            for j in range(i+2, min(i+5, len(lines))):
                val = lines[j].strip()
                if re.match(r'^\d{12}$', val):
                    return val
    
    # Pattern 2: Search for 12-digit standalone number
    for i, line in enumerate(lines[15:22]):
        val = line.strip()
        if re.match(r'^\d{12}$', val):
            return val
    
    return None

VENDOR_INVOICES['Apex Waste'] = {
    'format': 'NNNNNNNNNNNN',
    'examples': ['251030099185', '251115123456'],
    'extract': _extract_apex_waste_invoice
}


def _extract_ram_waste_invoice(text: str) -> Optional[str]:
    """Format: Waste Connections subsidiary - NNNNNNNVNNN
    Examples: 8931006V327
    
    OCR shows: INVOICE NO. at line 5, value at line 10
    """
    # Use Waste Connections extractor
    result = _extract_waste_connections_invoice(text)
    if result:
        return result
    
    lines = _split_lines(text)
    
    # Pattern 2: Find INVOICE NO. header
    for i, line in enumerate(lines[:10]):
        if line.strip() == 'INVOICE NO.':
            # Value is about 5 lines later
            for j in range(i+4, min(i+7, len(lines))):
                val = lines[j].strip()
                # Waste Connections format
                if re.match(r'^\d{7}[A-Z]\d{3}$', val):
                    return val
    
    return None

VENDOR_INVOICES['RAM Waste'] = {
    'format': 'NNNNNNNXNNN',
    'examples': ['8931006V327', '8945678V327'],
    'extract': _extract_ram_waste_invoice
}


def _extract_county_hauling_invoice(text: str) -> Optional[str]:
    """Format: CH + 7 digits
    Examples: CH1936902
    
    OCR shows: INVOICE NO. at line 10, value at line 15
    """
    lines = _split_lines(text)
    
    # Pattern 1: Find INVOICE NO. header
    for i, line in enumerate(lines):
        if line.strip() == 'INVOICE NO.':
            # Value is about 5 lines later
            for j in range(i+4, min(i+7, len(lines))):
                val = lines[j].strip()
                if re.match(r'^CH\d{7}$', val):
                    return val
    
    # Pattern 2: Direct pattern search
    match = re.search(r'\b(CH\d{7})\b', _normalize_text(text))
    if match:
        return match.group(1)
    
    return None

VENDOR_INVOICES['County Hauling'] = {
    'format': 'CHNNNNNNN',
    'examples': ['CH1936902', 'CH1876543'],
    'extract': _extract_county_hauling_invoice
}


def _extract_mark_dunning_invoice(text: str) -> Optional[str]:
    """Format: 8-character alphanumeric (mostly numeric, sometimes with letter)
    Examples: 59111926, 5A159781
    
    OCR shows: INVOICE# at line 0, value at line 1
    """
    lines = _split_lines(text)
    
    # Pattern 1: INVOICE# at line 0, value at line 1
    if len(lines) > 1:
        if 'INVOICE#' in lines[0].upper():
            val = lines[1].strip()
            # 8 characters: digits or one letter + digits
            if re.match(r'^[0-9A-Z]\d{7}$', val) or re.match(r'^\d[A-Z]\d{6}$', val) or re.match(r'^\d{8}$', val):
                return val
    
    # Pattern 2: Search for INVOICE# inline
    match = re.search(r'INVOICE#\s*([0-9A-Z]{8})', _normalize_text(text), re.I)
    if match:
        return match.group(1)
    
    return None

VENDOR_INVOICES['Mark Dunning'] = {
    'format': 'NNNNNNNN or XNNNNNNN',
    'examples': ['59111926', '5A159781'],
    'extract': _extract_mark_dunning_invoice
}


# ============================================================
# GENERIC FALLBACK PATTERNS
# For vendors not explicitly configured, try common patterns
# ============================================================

def _extract_generic_invoice(text: str) -> Optional[str]:
    """
    Generic invoice number extractor for unconfigured vendors.
    Tries common patterns in order of specificity.
    """
    lines = _split_lines(text)
    
    # Pattern 1: Invoice # NNNNNN (inline format - very common)
    match = re.search(r'Invoice\s*#\s*(\d{5,10})', _normalize_text(text), re.I)
    if match:
        return match.group(1)
    
    # Pattern 2: Invoice Number: NNNNNN
    match = re.search(r'Invoice\s*Number:?\s*(\d{5,12})', _normalize_text(text), re.I)
    if match:
        return match.group(1)
    
    # Pattern 3: Invoice No.: NNNNNN or INV prefix
    match = re.search(r'Invoice\s*No\.?:?\s*((?:INV)?\d{5,12})', _normalize_text(text), re.I)
    if match:
        return match.group(1)
    
    # Pattern 4: INVOICE #: or Invoice Number: followed by digits on next lines
    for i, line in enumerate(lines[:30]):
        if re.search(r'INVOICE\s*(#|NUMBER|NO\.?)\s*:?', line, re.I):
            # Check same line
            match = re.search(r'INVOICE\s*(?:#|NUMBER|NO\.?)\s*:?\s*(\d{5,12})', line, re.I)
            if match:
                return match.group(1)
            # Check next lines
            for j in range(i+1, min(i+5, len(lines))):
                val = lines[j].strip()
                if re.match(r'^\d{5,12}$', val):
                    return val
    
    # Pattern 5: ID# format (some haulers use this)
    match = re.search(r'ID#:?\s*(\d{6,12})', _normalize_text(text), re.I)
    if match:
        return match.group(1)
    
    # Pattern 6: Invoice followed by number (no # or :)
    match = re.search(r'Invoice\s+(\d{6,10})\b', _normalize_text(text), re.I)
    if match:
        return match.group(1)
    
    return None


# ============================================================
# TRANCHE 3 VENDORS
# ============================================================

def _extract_tower_compactor_invoice(text: str) -> Optional[str]:
    """Format: RENTAL-YY-NNNNN
    Examples: RENTAL-25-25941
    """
    lines = _split_lines(text)
    
    # Pattern 1: RENTAL-YY-NNNNN at line 6
    for i, line in enumerate(lines[:10]):
        val = line.strip()
        if re.match(r'^RENTAL-\d{2}-\d{5}$', val):
            return val
    
    # Pattern 2: Direct search
    match = re.search(r'\b(RENTAL-\d{2}-\d{5})\b', _normalize_text(text))
    if match:
        return match.group(1)
    
    return None

VENDOR_INVOICES['Tower Compactor'] = {
    'format': 'RENTAL-YY-NNNNN',
    'examples': ['RENTAL-25-25941', 'RENTAL-25-24567'],
    'extract': _extract_tower_compactor_invoice
}


def _extract_homewood_disposal_invoice(text: str) -> Optional[str]:
    """Format: Customer # NN-NNNNNN N
    Examples: 20-284298 5
    """
    lines = _split_lines(text)
    
    # Pattern 1: After Customer # header
    for i, line in enumerate(lines):
        if 'Customer #' in line:
            if i+1 < len(lines):
                val = lines[i+1].strip()
                # Format: NN-NNNNNN N
                match = re.match(r'^(\d{2}-\d{6}\s*\d?)$', val)
                if match:
                    return match.group(1).replace(' ', '')
    
    # Pattern 2: Direct search
    match = re.search(r'\b(\d{2}-\d{6})\b', _normalize_text(text))
    if match:
        return match.group(1)
    
    return None

VENDOR_INVOICES['Homewood Disposal'] = {
    'format': 'NN-NNNNNN',
    'examples': ['20-284298', '20-283456'],
    'extract': _extract_homewood_disposal_invoice
}


def _extract_kimble_invoice(text: str) -> Optional[str]:
    """Format: 10-digit numeric
    Examples: 0014297039
    
    OCR shows: INVOICE NO followed by value
    """
    lines = _split_lines(text)
    
    # Pattern 1: After INVOICE NO header
    for i, line in enumerate(lines):
        if line.strip() == 'INVOICE NO':
            if i+1 < len(lines):
                val = lines[i+1].strip()
                if re.match(r'^\d{10}$', val):
                    return val
    
    # Pattern 2: Direct search
    match = re.search(r'INVOICE\s*NO\s*(\d{10})', _normalize_text(text), re.I)
    if match:
        return match.group(1)
    
    return None

VENDOR_INVOICES['Kimble'] = {
    'format': 'NNNNNNNNNN',
    'examples': ['0014297039', '0014289012'],
    'extract': _extract_kimble_invoice
}


def _extract_delta_waste_invoice(text: str) -> Optional[str]:
    """Format: 5-digit at line 0 (NavuSoft style)
    Examples: 44166
    """
    lines = _split_lines(text)
    
    # Pattern 1: 5-digit at line 0
    if len(lines) > 0:
        val = lines[0].strip()
        if re.match(r'^\d{5}$', val):
            return val
    
    # Pattern 2: After INVOICE # header
    for i, line in enumerate(lines):
        if 'INVOICE #' in line.upper():
            # Check same line
            match = re.search(r'INVOICE\s*#:?\s*(\d{5,6})', line, re.I)
            if match:
                return match.group(1)
    
    return None

VENDOR_INVOICES['Delta Waste'] = {
    'format': 'NNNNN',
    'examples': ['44166', '43567'],
    'extract': _extract_delta_waste_invoice
}


def _extract_sbc_waste_invoice(text: str) -> Optional[str]:
    """Format: 6-digit numeric after Invoice Number header
    Examples: 795054, 803870
    
    OCR columnar format:
    Invoice Number  <- header at line 9
    ...
    <invoice_value>  <- at line 16
    """
    lines = _split_lines(text)
    
    # Pattern 1: Find Invoice Number header and get value 6-8 lines later
    for i, line in enumerate(lines):
        if line.strip() == 'Invoice Number':
            for j in range(i+5, min(i+10, len(lines))):
                val = lines[j].strip()
                if re.match(r'^\d{6}$', val):
                    return val
    
    # Pattern 2: Direct search
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{6})', _normalize_text(text), re.I)
    if match:
        return match.group(1)
    
    return None

VENDOR_INVOICES['SBC Waste'] = {
    'format': 'NNNNNN',
    'examples': ['795054', '803870'],
    'extract': _extract_sbc_waste_invoice
}


def _extract_national_equipment_invoice(text: str) -> Optional[str]:
    """Format: 6-digit after No: header
    Examples: 129508, 128954
    
    OCR format:
    No:  <- header at line 9
    Page:
    <invoice_value>  <- at line 11
    """
    lines = _split_lines(text)
    
    # Pattern 1: Find No: header and get value 2 lines later
    for i, line in enumerate(lines):
        if line.strip() == 'No:':
            # Check 2-3 lines later
            for j in range(i+2, min(i+4, len(lines))):
                val = lines[j].strip()
                if re.match(r'^\d{6}$', val):
                    return val
    
    # Pattern 2: Direct search
    match = re.search(r'No:?\s*(\d{6})', _normalize_text(text), re.I)
    if match:
        return match.group(1)
    
    return None

VENDOR_INVOICES['National Equipment Solutions'] = {
    'format': 'NNNNNN',
    'examples': ['129508', '128954'],
    'extract': _extract_national_equipment_invoice
}


def _extract_el_harvey_invoice(text: str) -> Optional[str]:
    """Format: Waste Connections subsidiary - NNNNNNNXNNN
    Examples: 2028735W390, 2038776W390
    """
    # Use Waste Connections pattern
    return _extract_waste_connections_invoice(text)

VENDOR_INVOICES['EL Harvey'] = {
    'format': 'NNNNNNNXNNN',
    'examples': ['2028735W390', '2038776W390'],
    'extract': _extract_el_harvey_invoice
}


def _extract_specific_waste_invoice(text: str) -> Optional[str]:
    """Format: 7-digit numeric
    Examples: 9063228, 1730973
    
    OCR formats:
    1. Certificate format: 7-digit at line 1
    2. Order format: Order # header at line 10, value at line 12
    """
    lines = _split_lines(text)
    
    # Pattern 1: Find Order # header
    for i, line in enumerate(lines[:15]):
        if line.strip() == 'Order #':
            # Value is 2 lines later
            for j in range(i+1, min(i+4, len(lines))):
                val = lines[j].strip()
                if re.match(r'^\d{7}$', val):
                    return val
    
    # Pattern 2: 7-digit at line 1
    if len(lines) > 1:
        val = lines[1].strip()
        if re.match(r'^\d{7}$', val):
            return val
    
    # Pattern 3: Search first 15 lines for 7-digit
    for i in range(min(15, len(lines))):
        val = lines[i].strip()
        if re.match(r'^\d{7}$', val):
            return val
    
    return None

VENDOR_INVOICES['Specific Waste'] = {
    'format': 'NNNNNNN',
    'examples': ['9063228', '9054567'],
    'extract': _extract_specific_waste_invoice
}


def _extract_wasatch_waste_invoice(text: str) -> Optional[str]:
    """Format: INV + 5-6 digits OR account number
    Examples: INV70978
    """
    # Pattern 1: INV prefix
    match = re.search(r'\b(INV\d{5,6})\b', _normalize_text(text))
    if match:
        return match.group(1)
    
    # Pattern 2: Standard invoice pattern
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', _normalize_text(text), re.I)
    if match:
        return match.group(1)
    
    return None

VENDOR_INVOICES['Wasatch Waste'] = {
    'format': 'INVNNNNN',
    'examples': ['INV70978', 'INV69543'],
    'extract': _extract_wasatch_waste_invoice
}


def _extract_empire_waste_invoice(text: str) -> Optional[str]:
    """Format: 6-digit at line 0 (NavuSoft style)
    Examples: 215991
    """
    lines = _split_lines(text)
    
    # Pattern 1: 6-digit at line 0
    if len(lines) > 0:
        val = lines[0].strip()
        if re.match(r'^\d{6}$', val):
            return val
    
    # Pattern 2: After INVOICE # header
    for i, line in enumerate(lines):
        if 'INVOICE #' in line.upper():
            match = re.search(r'INVOICE\s*#:?\s*(\d{5,8})', line, re.I)
            if match:
                return match.group(1)
    
    return None

VENDOR_INVOICES['Empire Waste'] = {
    'format': 'NNNNNN',
    'examples': ['215991', '214567'],
    'extract': _extract_empire_waste_invoice
}


def _extract_apex_waste_invoice(text: str) -> Optional[str]:
    """Format: Various
    """
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', _normalize_text(text), re.I)
    if match:
        return match.group(1)
    
    return None

VENDOR_INVOICES['Apex Waste'] = {
    'format': 'NNNNNNN',
    'examples': ['1234567'],
    'extract': _extract_apex_waste_invoice
}


def _extract_aces_disposal_invoice(text: str) -> Optional[str]:
    """Format: 5-6 digit invoice OR 8-10 digit tracking/reference
    Examples: 55391, 94975882
    
    Multiple formats:
    1. Invoice # columnar header
    2. Reference Number (10-digit)
    3. Tracking number in text
    4. INVOICE# inline (Proware format)
    """
    lines = _split_lines(text)
    
    # Pattern 1: INVOICE# inline (Proware format)
    match = re.search(r'INVOICE#\s*(\d{5,6})', _normalize_text(text), re.I)
    if match:
        return match.group(1)
    
    # Pattern 2: Find Invoice # header and look below
    for i, line in enumerate(lines):
        if line.strip() == 'Invoice #':
            for j in range(i+5, min(i+10, len(lines))):
                val = lines[j].strip()
                if re.match(r'^\d{5,6}$', val):
                    return val
    
    # Pattern 3: Reference Number for payment receipts
    for i, line in enumerate(lines):
        if 'Reference Number' in line:
            if i+1 < len(lines):
                val = lines[i+1].strip()
                if re.match(r'^\d{10}$', val):
                    return val
    
    # Pattern 4: Tracking number in text
    match = re.search(r'tracking number.*?is\s+(\d{8})', _normalize_text(text), re.I)
    if match:
        return match.group(1)
    
    return None

VENDOR_INVOICES['ACES Disposal'] = {
    'format': 'NNNNN(N) or NNNNNNNN',
    'examples': ['55391', '94975882'],
    'extract': _extract_aces_disposal_invoice
}


def _extract_atlas_disposal_invoice(text: str) -> Optional[str]:
    """Format: Account number as ID NN-NNNNNNN
    Examples: 01-0202488
    
    OCR shows: Account #: at line 4, value at line 12
    """
    lines = _split_lines(text)
    
    # Pattern 1: After Account #: header
    for i, line in enumerate(lines[:10]):
        if 'Account #' in line:
            for j in range(i+5, min(i+10, len(lines))):
                val = lines[j].strip()
                # Format: NN-NNNNNNN
                if re.match(r'^\d{2}-\d{7}$', val):
                    return val
    
    # Pattern 2: Direct pattern search
    match = re.search(r'\b(\d{2}-\d{7})\b', _normalize_text(text))
    if match:
        return match.group(1)
    
    return None

VENDOR_INVOICES['Atlas Disposal'] = {
    'format': 'NN-NNNNNNN',
    'examples': ['01-0202488', '02-1234567'],
    'extract': _extract_atlas_disposal_invoice
}


def _extract_121_disposal_invoice(text: str) -> Optional[str]:
    """Format: 9-digit Transaction Number OR INV + 6 digits
    Examples: 328220153, INV171040, INV196191
    
    Multiple formats:
    1. Payment receipt: Transaction Number
    2. Invoice: Document # or Invoice # with INV prefix
    """
    lines = _split_lines(text)
    
    # Pattern 1: Invoice # header at line 1, value at line 2
    for i, line in enumerate(lines[:5]):
        if line.strip() == 'Invoice #':
            if i+1 < len(lines):
                val = lines[i+1].strip()
                if re.match(r'^INV\d{6}$', val):
                    return val
    
    # Pattern 2: Document # header with INV value below
    for i, line in enumerate(lines):
        if line.strip() == 'Document #':
            for j in range(i+1, min(i+5, len(lines))):
                val = lines[j].strip()
                if re.match(r'^INV\d{6}$', val):
                    return val
    
    # Pattern 3: Transaction Number header (payment receipt)
    for i, line in enumerate(lines):
        if 'Transaction Number' in line:
            if i+1 < len(lines):
                val = lines[i+1].strip()
                if re.match(r'^\d{9}$', val):
                    return val
    
    # Pattern 4: Payment Successful [NNNNNNNNN] format
    match = re.search(r'Payment Successful\s*\[(\d{9})\]', _normalize_text(text))
    if match:
        return match.group(1)
    
    # Pattern 5: Direct search for INV format
    match = re.search(r'\b(INV\d{6})\b', _normalize_text(text))
    if match:
        return match.group(1)
    
    return None

VENDOR_INVOICES['121 Disposal'] = {
    'format': 'NNNNNNNNN or INVNNNNNN',
    'examples': ['328220153', 'INV171040'],
    'extract': _extract_121_disposal_invoice
}


def _extract_five_star_waste_invoice(text: str) -> Optional[str]:
    """Format: 5-digit numeric
    Examples: 47292
    
    OCR shows: INVOICE # at line 3, value at line 9
    """
    lines = _split_lines(text)
    
    # Pattern 1: Find INVOICE # header
    for i, line in enumerate(lines[:8]):
        if line.strip() == 'INVOICE #':
            # Value is about 5-6 lines later
            for j in range(i+4, min(i+8, len(lines))):
                val = lines[j].strip()
                if re.match(r'^\d{5}$', val):
                    return val
    
    # Pattern 2: Look at line 9 directly
    if len(lines) > 9:
        val = lines[9].strip()
        if re.match(r'^\d{5}$', val):
            return val
    
    return None

VENDOR_INVOICES['Five Star Waste'] = {
    'format': 'NNNNN',
    'examples': ['47292', '45678'],
    'extract': _extract_five_star_waste_invoice
}


def _extract_patriot_waste_invoice(text: str) -> Optional[str]:
    """Format: 10-digit numeric
    Examples: 0000230872
    
    OCR shows: INVOICE NO. at line 7, value at line 13
    """
    lines = _split_lines(text)
    
    # Pattern 1: Find INVOICE NO. header
    for i, line in enumerate(lines[:12]):
        if line.strip() == 'INVOICE NO.':
            # Value is about 6 lines later
            for j in range(i+4, min(i+8, len(lines))):
                val = lines[j].strip()
                if re.match(r'^\d{10}$', val):
                    return val
    
    # Pattern 2: Look at line 13 directly
    if len(lines) > 13:
        val = lines[13].strip()
        if re.match(r'^\d{10}$', val):
            return val
    
    return None

VENDOR_INVOICES['Patriot Waste'] = {
    'format': 'NNNNNNNNNN',
    'examples': ['0000230872', '0000245678'],
    'extract': _extract_patriot_waste_invoice
}


def _extract_wise_environmental_invoice(text: str) -> Optional[str]:
    """Format: 9-digit numeric OR 6-digit at line 0
    Examples: 202521189, 284990
    
    Multiple formats:
    1. Invoice # header with 9-digit value
    2. Earthwise format: 6-digit at line 0
    """
    lines = _split_lines(text)
    
    # Pattern 1: 6-digit at line 0 (Earthwise format)
    if len(lines) > 0:
        val = lines[0].strip()
        if re.match(r'^\d{6}$', val):
            return val
    
    # Pattern 2: Find Invoice # header (Wise format)
    for i, line in enumerate(lines):
        if line.strip() == 'Invoice #':
            for j in range(i+4, min(i+8, len(lines))):
                val = lines[j].strip()
                if re.match(r'^\d{9}$', val):
                    return val
    
    # Pattern 3: INVOICE # header (Earthwise format)
    for i, line in enumerate(lines[:15]):
        if line.strip() == 'INVOICE #':
            # Value might be before (columnar)
            for j in range(max(0, i-6), i):
                val = lines[j].strip()
                if re.match(r'^\d{6}$', val):
                    return val
    
    # Pattern 4: Search for 9-digit standalone
    for i, line in enumerate(lines[30:45]):
        val = line.strip()
        if re.match(r'^\d{9}$', val):
            return val
    
    return None

VENDOR_INVOICES['Wise Environmental'] = {
    'format': 'NNNNNNNNN or NNNNNN',
    'examples': ['202521189', '284990'],
    'extract': _extract_wise_environmental_invoice
}


def _extract_ace_recycling_invoice(text: str) -> Optional[str]:
    """Format: 7-digit numeric at line 0
    Examples: 1162376
    
    Columnar format: value at line 0, INVOICE # header at line 7
    """
    lines = _split_lines(text)
    
    # Pattern 1: 7-digit at line 0
    if len(lines) > 0:
        val = lines[0].strip()
        if re.match(r'^\d{7}$', val):
            return val
    
    # Pattern 2: Find INVOICE # header and look before
    for i, line in enumerate(lines[:15]):
        if line.strip() == 'INVOICE #':
            for j in range(max(0, i-8), i):
                val = lines[j].strip()
                if re.match(r'^\d{7}$', val):
                    return val
    
    return None

VENDOR_INVOICES['Ace Recycling'] = {
    'format': 'NNNNNNN',
    'examples': ['1162376', '1154321'],
    'extract': _extract_ace_recycling_invoice
}


def _extract_texas_disposal_invoice(text: str) -> Optional[str]:
    """Format: 7-digit numeric
    Examples: 8701913
    
    OCR shows: Invoice # at line 3, value at line 5
    """
    lines = _split_lines(text)
    
    # Pattern 1: Find Invoice # header
    for i, line in enumerate(lines[:8]):
        if line.strip() == 'Invoice #':
            # Value is 2 lines later
            for j in range(i+1, min(i+4, len(lines))):
                val = lines[j].strip()
                if re.match(r'^\d{7}$', val):
                    return val
    
    # Pattern 2: Look at line 5 directly
    if len(lines) > 5:
        val = lines[5].strip()
        if re.match(r'^\d{7}$', val):
            return val
    
    return None

VENDOR_INVOICES['Texas Disposal'] = {
    'format': 'NNNNNNN',
    'examples': ['8701913', '8654321'],
    'extract': _extract_texas_disposal_invoice
}


def _extract_ghw_waste_invoice(text: str) -> Optional[str]:
    """Format: G + 7 digits
    Examples: G1108208
    
    OCR shows: INVOICE NO. at line 10, value at line 11
    """
    lines = _split_lines(text)
    
    # Pattern 1: Find INVOICE NO. header
    for i, line in enumerate(lines[:15]):
        if line.strip() == 'INVOICE NO.':
            if i+1 < len(lines):
                val = lines[i+1].strip()
                if re.match(r'^G\d{7}$', val):
                    return val
    
    # Pattern 2: Direct search for G prefix
    match = re.search(r'\b(G\d{7})\b', _normalize_text(text))
    if match:
        return match.group(1)
    
    return None

VENDOR_INVOICES['GHW Waste'] = {
    'format': 'GNNNNNNN',
    'examples': ['G1108208', 'G1234567'],
    'extract': _extract_ghw_waste_invoice
}


def _extract_usa_waste_invoice(text: str) -> Optional[str]:
    """Format: 10-digit numeric
    Examples: 4202731981, 4202773007
    
    Multiple formats:
    1. INVOICE # inline format
    2. Invoice Number columnar - header at line 1, value at line 8
    """
    lines = _split_lines(text)
    
    # Pattern 1: Find Invoice Number header and get value below
    for i, line in enumerate(lines[:5]):
        if line.strip() == 'Invoice Number':
            for j in range(i+5, min(i+10, len(lines))):
                val = lines[j].strip()
                if re.match(r'^\d{10}$', val):
                    return val
    
    # Pattern 2: INVOICE # inline format
    match = re.search(r'INVOICE\s*#\s*(\d{10})', _normalize_text(text), re.I)
    if match:
        return match.group(1)
    
    return None

VENDOR_INVOICES['USA Waste'] = {
    'format': 'NNNNNNNNNN',
    'examples': ['4202731981', '4202773007'],
    'extract': _extract_usa_waste_invoice
}


def _extract_city_of_meridian_invoice(text: str) -> Optional[str]:
    """Format: 7-digit Statement No
    Examples: 4387420
    
    OCR shows: Statement No: at line 5, value at line 6
    """
    lines = _split_lines(text)
    
    # Pattern 1: Find Statement No: header
    for i, line in enumerate(lines[:10]):
        if 'Statement No:' in line:
            if i+1 < len(lines):
                val = lines[i+1].strip()
                if re.match(r'^\d{7}$', val):
                    return val
    
    # Pattern 2: Statement No: inline
    match = re.search(r'Statement\s*No:?\s*(\d{7})', _normalize_text(text), re.I)
    if match:
        return match.group(1)
    
    return None

VENDOR_INVOICES['City of Meridian'] = {
    'format': 'NNNNNNN',
    'examples': ['4387420', '4312345'],
    'extract': _extract_city_of_meridian_invoice
}


def _extract_becker360_invoice(text: str) -> Optional[str]:
    """Format: PS-INV + 6 digits
    Examples: PS-INV203951
    
    OCR shows value at line 1
    """
    lines = _split_lines(text)
    
    # Pattern 1: PS-INV at line 1
    if len(lines) > 1:
        val = lines[1].strip()
        if re.match(r'^PS-INV\d{6}$', val):
            return val
    
    # Pattern 2: Direct search
    match = re.search(r'\b(PS-INV\d{6})\b', _normalize_text(text))
    if match:
        return match.group(1)
    
    return None

VENDOR_INVOICES['Becker360'] = {
    'format': 'PS-INVNNNNNN',
    'examples': ['PS-INV203951', 'PS-INV198765'],
    'extract': _extract_becker360_invoice
}


def _extract_ssw_frontload_invoice(text: str) -> Optional[str]:
    """Format: 6-digit numeric
    Examples: 215983
    
    OCR shows: Invoice 215983 at line 0
    """
    lines = _split_lines(text)
    
    # Pattern 1: Invoice + number at line 0
    if len(lines) > 0:
        match = re.match(r'^Invoice\s+(\d{6})$', lines[0].strip(), re.I)
        if match:
            return match.group(1)
    
    # Pattern 2: Invoice inline
    match = re.search(r'Invoice\s+(\d{6})\b', _normalize_text(text), re.I)
    if match:
        return match.group(1)
    
    return None

VENDOR_INVOICES['SSW Frontload'] = {
    'format': 'NNNNNN',
    'examples': ['215983', '214567'],
    'extract': _extract_ssw_frontload_invoice
}


def _extract_louisiana_waste_invoice(text: str) -> Optional[str]:
    """Format: 5-digit at line 0
    Examples: 67826
    
    Columnar format: value at line 0, INVOICE # header at line 11
    """
    lines = _split_lines(text)
    
    # Pattern 1: 5-digit at line 0
    if len(lines) > 0:
        val = lines[0].strip()
        if re.match(r'^\d{5}$', val):
            return val
    
    # Pattern 2: Find INVOICE # header and look before
    for i, line in enumerate(lines[:15]):
        if line.strip() == 'INVOICE #':
            for j in range(max(0, i-12), i):
                val = lines[j].strip()
                if re.match(r'^\d{5}$', val):
                    return val
    
    return None

VENDOR_INVOICES['Louisiana Waste'] = {
    'format': 'NNNNN',
    'examples': ['67826', '65432'],
    'extract': _extract_louisiana_waste_invoice
}


def _extract_1800_got_junk_invoice(text: str) -> Optional[str]:
    """Format: INV + 6 digits
    Examples: INV258126
    
    OCR shows value at line 1
    """
    lines = _split_lines(text)
    
    # Pattern 1: INV at line 1
    if len(lines) > 1:
        val = lines[1].strip()
        if re.match(r'^INV\d{6}$', val):
            return val
    
    # Pattern 2: Direct search
    match = re.search(r'\b(INV\d{6})\b', _normalize_text(text))
    if match:
        return match.group(1)
    
    return None

VENDOR_INVOICES['1-800-Got-Junk'] = {
    'format': 'INVNNNNNN',
    'examples': ['INV258126', 'INV245678'],
    'extract': _extract_1800_got_junk_invoice
}


def _extract_independent_recycling_invoice(text: str) -> Optional[str]:
    """Format: 10-digit
    Examples: 0000630097
    
    OCR shows: INVOICE NO. at line 10, value at line 16
    """
    lines = _split_lines(text)
    
    # Pattern 1: Find INVOICE NO. header
    for i, line in enumerate(lines[:15]):
        if line.strip() == 'INVOICE NO.':
            for j in range(i+4, min(i+8, len(lines))):
                val = lines[j].strip()
                if re.match(r'^\d{10}$', val):
                    return val
    
    # Pattern 2: Look for 10-digit in lines 15-20
    for i in range(14, min(20, len(lines))):
        val = lines[i].strip()
        if re.match(r'^\d{10}$', val):
            return val
    
    return None

VENDOR_INVOICES['Independent Recycling'] = {
    'format': 'NNNNNNNNNN',
    'examples': ['0000630097', '0000654321'],
    'extract': _extract_independent_recycling_invoice
}


def _extract_gotta_go_waste_invoice(text: str) -> Optional[str]:
    """Format: 10-digit
    Examples: 0000125701
    
    OCR shows: Invoice at line 6, value at line 12
    """
    lines = _split_lines(text)
    
    # Pattern 1: Find Invoice header and get value below
    for i, line in enumerate(lines[:10]):
        if line.strip() == 'Invoice':
            for j in range(i+4, min(i+8, len(lines))):
                val = lines[j].strip()
                if re.match(r'^\d{10}$', val):
                    return val
    
    # Pattern 2: Look for 10-digit in lines 10-15
    for i in range(10, min(16, len(lines))):
        val = lines[i].strip()
        if re.match(r'^\d{10}$', val):
            return val
    
    return None

VENDOR_INVOICES['Gotta Go Waste'] = {
    'format': 'NNNNNNNNNN',
    'examples': ['0000125701', '0000123456'],
    'extract': _extract_gotta_go_waste_invoice
}


# ============================================================
# PUBLIC API
# ============================================================

def extract_invoice_number(vendor_name: str, text: str) -> Optional[str]:
    """
    Extract invoice number from invoice text for a given vendor.
    
    DETERMINISTIC: Returns exact match or None. No guessing.
    
    Args:
        vendor_name: The detected vendor name (from vendor_detection_module)
        text: The raw OCR text from the invoice
        
    Returns:
        str or None - The extracted invoice number, or None if not found
    """
    if vendor_name in VENDOR_INVOICES:
        return VENDOR_INVOICES[vendor_name]['extract'](text)
    
    # Try generic extraction for unconfigured vendors
    return _extract_generic_invoice(text)


def get_invoice_format(vendor_name: str) -> Optional[Dict[str, Any]]:
    """
    Get the invoice number format description for a vendor.
    
    Returns:
        dict with keys: format, examples
        or None if vendor not configured
    """
    if vendor_name not in VENDOR_INVOICES:
        return None
    
    config = VENDOR_INVOICES[vendor_name]
    return {
        'format': config['format'],
        'examples': config['examples']
    }


def get_configured_vendors() -> List[str]:
    """Return list of all vendors with invoice extraction configured."""
    return list(VENDOR_INVOICES.keys())


def get_vendor_stats() -> Dict[str, int]:
    """Return summary statistics of configured vendors."""
    return {
        'total_configured': len(VENDOR_INVOICES)
    }


# ============================================================
# COMBINED EXTRACTION API (Account + Invoice)
# ============================================================

def extract_both(vendor_name: str, text: str) -> Dict[str, Optional[str]]:
    """
    Extract both account number and invoice number from invoice text.
    
    This is the recommended entry point for combined extraction.
    
    Args:
        vendor_name: The detected vendor name
        text: The raw OCR text from the invoice
        
    Returns:
        dict with keys: account_number, invoice_number
    """
    # Import account extraction (defer to avoid circular imports)
    try:
        from account_extraction_engine_v3 import extract_account
        account = extract_account(vendor_name, text)
    except ImportError:
        account = None
    
    invoice = extract_invoice_number(vendor_name, text)
    
    return {
        'account_number': account,
        'invoice_number': invoice
    }


# ============================================================
# MAIN - Testing and Validation
# ============================================================

if __name__ == '__main__':
    print("Invoice Number Extraction Engine v1.0")
    print("=" * 70)
    
    stats = get_vendor_stats()
    print(f"Total configured vendors: {stats['total_configured']}")
    
    print("\n" + "=" * 70)
    print("VENDOR INVOICE FORMATS (Alphabetical)")
    print("=" * 70)
    
    for vendor, config in sorted(VENDOR_INVOICES.items()):
        fmt = config.get('format', 'Unknown')
        examples = config.get('examples', [])
        example_str = ', '.join(examples[:2]) if examples else 'N/A'
        print(f"  {vendor}: {fmt} (e.g., {example_str})")
