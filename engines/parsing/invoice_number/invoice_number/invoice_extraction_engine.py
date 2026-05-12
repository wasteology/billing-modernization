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

    # Normalize text to handle literal \n strings
    normalized = _normalize_text(text)
    lines = normalized.split('\n')

    # Pattern 1: "INVOICE NUMBER:" format (10 digits) - check first occurrence
    match = re.search(r'INVOICE\s*NUMBER:\s*(\d{10})', normalized, re.I)
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
    """Format: 7-digit invoice number

    Capital Waste invoice format:
    - INVOICE: 7-digit (e.g., 2716684, 2711847)
    - ACCOUNT: 5-6 digit (e.g., 141381, 166509)

    OCR shows columnar headers:
    INVOICE
    AMOUNT
    ACCOUNT
    DATE
    DUE DATE
    2716684       <- invoice value (first after headers)
    $81.65        <- amount
    141381        <- account
    """
    lines = _split_lines(text)

    # Pattern 1: Find INVOICE header (standalone) and get 7-digit value after
    for i, line in enumerate(lines):
        if line.strip() == 'INVOICE':
            # Search next 8 lines for 7-digit number (skip amount which has $)
            for j in range(i+1, min(i+8, len(lines))):
                val = lines[j].strip()
                # Skip lines with $ (amounts), dates, etc.
                if re.match(r'^\d{7}$', val):
                    return val

    # Pattern 2: Search for 7-digit number near INVOICE keyword
    match = re.search(r'INVOICE\s*\n?\s*(?:AMOUNT\s*\n?\s*)?(?:ACCOUNT\s*\n?\s*)?(?:DATE\s*\n?\s*)?(?:DUE DATE\s*\n?\s*)?(\d{7})', _normalize_text(text), re.I)
    if match:
        return match.group(1)

    return None
    
    # Pattern 4: Standard invoice pattern
    match = re.search(r'Invoice\s*(?:#|No\.?|Number)?:?\s*(\d{5,10})', _normalize_text(text), re.I)
    if match:
        return match.group(1)
    
    return None

VENDOR_INVOICES['Capital Waste'] = {
    'format': 'NNNNNNN (7-digit) or NNNNNNNNNN (10-digit) or CH prefix',
    'examples': ['2716684', '0001341438', 'CH0001347121'],
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
    """Format: 6-digit invoice number (Invoice NNNNNN)
    Examples: 133033, 136509, 137678

    Navajo Sanitation invoices have:
    - ID#: 12-digit customer account (e.g., 577170008807)
    - Invoice: 6-digit invoice number (e.g., 133033)

    NOTE: The ID# is the account number, NOT the invoice number.
    The actual invoice number appears after 'Invoice' keyword.
    """
    # Priority 1: Invoice + 5-6 digit number (the actual invoice number)
    match = re.search(r'Invoice\s+(\d{5,6})\b', _normalize_text(text), re.I)
    if match:
        return match.group(1)

    # Pattern 2: Invoice ##### Total (sometimes at end of document)
    match = re.search(r'Invoice\s+(\d{5,6})\s+Total', _normalize_text(text), re.I)
    if match:
        return match.group(1)

    return None

VENDOR_INVOICES['Navajo Sanitation'] = {
    'format': 'NNNNNN (5-6 digit)',
    'examples': ['133033', '136509', '137678'],
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
    
    # Pattern 4: INVOICE NUMBER: with alphanumeric value (e.g., 0245139-IN)
    match = re.search(r'INVOICE\s*NUMBER:?\s*([A-Z0-9]+-[A-Z0-9]+|\d{6,12})', _normalize_text(text), re.I)
    if match:
        return match.group(1)
    
    # Pattern 5: INVOICE# with alphanumeric value (e.g., 5CF02219, 54X25685)
    match = re.search(r'INVOICE\s*#:?\s*([A-Z0-9]{6,12})', _normalize_text(text), re.I)
    if match:
        val = match.group(1)
        # Skip if it's just "STATEMENT" or similar
        if val.upper() not in ['STATEMENT', 'NUMBER', 'DATE']:
            return val
    
    # Pattern 6: INVOICE #: or Invoice Number: followed by digits on next lines (columnar)
    for i, line in enumerate(lines[:30]):
        if re.search(r'INVOICE\s*(#|NUMBER|NO\.?)\s*:?', line, re.I):
            # Check same line
            match = re.search(r'INVOICE\s*(?:#|NUMBER|NO\.?)\s*:?\s*(\d{5,12})', line, re.I)
            if match:
                return match.group(1)
            # Check next lines for numeric or alphanumeric
            for j in range(i+1, min(i+5, len(lines))):
                val = lines[j].strip()
                if re.match(r'^\d{5,12}$', val):
                    return val
                # Alphanumeric like 0245139-IN or 5CF02219
                if re.match(r'^[A-Z0-9]{5,12}(-[A-Z0-9]+)?$', val) and val.upper() not in ['STATEMENT', 'NUMBER', 'DATE', 'TOTAL']:
                    return val
    
    # Pattern 7: ID# format (some haulers use this)
    match = re.search(r'ID#:?\s*(\d{6,12})', _normalize_text(text), re.I)
    if match:
        return match.group(1)
    
    # Pattern 8: Invoice followed by number (no # or :)
    match = re.search(r'Invoice\s+(\d{6,10})\b', _normalize_text(text), re.I)
    if match:
        return match.group(1)
    
    # Pattern 9: Invoice # with alphanumeric value on same line (e.g., Invoice # 40191INV)
    match = re.search(r'Invoice\s*#\s*([A-Z0-9]{5,12})', _normalize_text(text), re.I)
    if match:
        val = match.group(1)
        if val.upper() not in ['STATEMENT', 'NUMBER', 'DATE']:
            return val
    
    # Pattern 10: Columnar format - "Invoice #" header at line N, value at line N+4 to N+6
    for i, line in enumerate(lines[:20]):
        if line.strip() in ['Invoice #', 'INVOICE #', 'Invoice#', 'INVOICE#']:
            for j in range(i+3, min(i+7, len(lines))):
                val = lines[j].strip()
                if re.match(r'^[A-Z0-9]{5,12}(INV)?$', val) and val.upper() not in ['STATEMENT', 'NUMBER', 'DATE', 'TOTAL']:
                    return val
    
    # Pattern 11: INV-NNNNNN or INV prefix patterns
    match = re.search(r'\b(INV[-]?\d{5,10})\b', _normalize_text(text), re.I)
    if match:
        return match.group(1)
    
    # Pattern 12: GA prefix (Amwaste format: GA 0000466397)
    match = re.search(r'INVOICE\s*#:?\s*([A-Z]{2}\s*\d{7,12})', _normalize_text(text), re.I)
    if match:
        return match.group(1).replace(' ', '')
    
    # Pattern 13: Reference #/Number with digits
    match = re.search(r'Reference\s*(?:#|Number):?\s*(\d{6,12})', _normalize_text(text), re.I)
    if match:
        return match.group(1)
    
    # Pattern 14: Document # or Doc #
    match = re.search(r'Doc(?:ument)?\s*#:?\s*(\d{5,12})', _normalize_text(text), re.I)
    if match:
        return match.group(1)
    
    # Pattern 15: Transaction # or Trans #
    match = re.search(r'Trans(?:action)?\s*(?:#|Number):?\s*(\d{6,12})', _normalize_text(text), re.I)
    if match:
        return match.group(1)
    
    # Pattern 16: CN prefix (Coastal Waste: CN0001018628)
    match = re.search(r'\b(CN\d{10})\b', _normalize_text(text))
    if match:
        return match.group(1)
    
    # Pattern 17: GC prefix (Gulf Coast: GC0000164335)
    match = re.search(r'\b(GC\d{10})\b', _normalize_text(text))
    if match:
        return match.group(1)
    
    # Pattern 18: Ticket # for scale tickets (if no invoice found)
    match = re.search(r'TICKET\s*#?\s*(\d{6,10})', _normalize_text(text), re.I)
    if match:
        return match.group(1)
    
    # Pattern 19: Statement/Account with inline number (Western Disposal style)
    # Skip if just account number without invoice
    
    # Pattern 20: Order # (Specialty Pallet, some haulers)
    match = re.search(r'Order\s*#:?\s*(\d{5,10})', _normalize_text(text), re.I)
    if match:
        return match.group(1)
    
    # Pattern 21: PO # as fallback for haul tickets
    match = re.search(r'\bPO[:#]?\s*(\d{5,10})\b', _normalize_text(text))
    if match:
        return match.group(1)
    
    # Pattern 22: INVOICE header followed by number on next line (Mac's Wood format)
    for i, line in enumerate(lines[:25]):
        if line.strip().upper() == 'INVOICE':
            # Check next line for number
            if i+1 < len(lines):
                val = lines[i+1].strip()
                if re.match(r'^\d{4,10}$', val):
                    return val
    
    # Pattern 23: ID#: NNNNNNNNN format (TrashBilling style: 122370006157)
    match = re.search(r'ID#?:?\s*(\d{10,15})', _normalize_text(text))
    if match:
        return match.group(1)
    
    # Pattern 24: Statement No: or Statement Number  
    match = re.search(r'Statement\s*(?:No\.?|Number|#):?\s*(\d{5,12})', _normalize_text(text), re.I)
    if match:
        return match.group(1)
    
    # Pattern 25: Account Number as last resort for utility-style invoices
    # Only if it looks like an invoice (has amount due, charges, etc)
    if 'AMOUNT DUE' in text.upper() or 'CURRENT CHARGES' in text.upper():
        match = re.search(r'Account\s*(?:Number|#|No\.?):?\s*(\d{6,15})', _normalize_text(text), re.I)
        if match:
            return match.group(1)
    
    # Pattern 26: Invoice #NNNN (# attached to Invoice with no space)
    match = re.search(r'Invoice\s*#(\d{4,10})', _normalize_text(text), re.I)
    if match:
        return match.group(1)
    
    # Pattern 27: Alphanumeric invoice with dash (PT-25-01048, IN-123456)
    match = re.search(r'Invoice\s*(?:#|No\.?|Number)?:?\s*([A-Z]{1,3}-\d{2}-\d{4,8})', _normalize_text(text), re.I)
    if match:
        return match.group(1)
    
    # Pattern 28: INVOICE: NNNNNN (colon after INVOICE)
    match = re.search(r'INVOICE:\s*(\d{5,12})', _normalize_text(text), re.I)
    if match:
        return match.group(1)
    
    # Pattern 29: NavuSoft extended columnar - INVOICE NO at line N, value at line N+10 to N+15
    for i, line in enumerate(lines[:15]):
        if line.strip().upper() in ['INVOICE NO', 'INVOICE NO.']:
            # Search for value up to 15 lines after
            for j in range(i+3, min(i+16, len(lines))):
                val = lines[j].strip()
                if re.match(r'^\d{5,10}$', val):
                    return val
                # Also check for Waste Connections format (digits + letter + digits)
                if re.match(r'^\d{6,10}[A-Z]\d{2,4}$', val):
                    return val
    
    # Pattern 30: Service Order/Work Order number as fallback
    match = re.search(r'(?:Service|Work)\s*Order\s*(?:#|No\.?)?:?\s*(\d{4,10})', _normalize_text(text), re.I)
    if match:
        return match.group(1)
    
    # Pattern 31: Invoice No: with alphanumeric-dash format (2520777-IN, 7572)
    match = re.search(r'Invoice\s*No:?\s*([A-Z0-9]+-[A-Z0-9]+|\d{4,10})', _normalize_text(text), re.I)
    if match:
        return match.group(1)
    
    # Pattern 32: Invoice/Statement No. with dash format (9298-140)
    match = re.search(r'Invoice/Statement\s*No\.?\s*(\d+-\d+)', _normalize_text(text), re.I)
    if match:
        return match.group(1)
    
    # Pattern 33: Invoice Nbr: format
    match = re.search(r'Invoice\s*Nbr:?\s*(\d{5,10})', _normalize_text(text), re.I)
    if match:
        return match.group(1)
    
    # Pattern 34: WM Solutions format (NNNNNNN-NNNN-N)
    match = re.search(r'Invoice\s*Number\s*(\d{7}-\d{4}-\d)', _normalize_text(text), re.I)
    if match:
        return match.group(1)
    
    # Pattern 35: Columnar "Invoice Number" header with value on next lines
    for i, line in enumerate(lines[:20]):
        if 'Invoice Number' in line or 'INVOICE NUMBER' in line:
            for j in range(i+1, min(i+6, len(lines))):
                val = lines[j].strip()
                # Standard numeric
                if re.match(r'^\d{6,12}$', val):
                    return val
                # With dashes (0019791-1962-3)
                if re.match(r'^\d{7}-\d{4}-\d$', val):
                    return val
    
    # Pattern 36: "Invoice NNNNN" after vendor name (Marcotte style)
    match = re.search(r'Invoice\s+(\d{5,8})\s*$', _normalize_text(text), re.I | re.M)
    if match:
        return match.group(1)
    
    # Pattern 37: MONTH INVOICE YEAR with invoice number below (00001069-1025)
    match = re.search(r'INVOICE\s*(\d{8}-\d{4})', _normalize_text(text))
    if match:
        return match.group(1)
    
    # Pattern 38: Invoice # with dash (477-1)
    match = re.search(r'Invoice\s*#\s*(\d+-\d+)', _normalize_text(text), re.I)
    if match:
        return match.group(1)
    
    # Pattern 39: No. NNNNN format (Canusa style: No. 62370)
    match = re.search(r'\bNo\.\s*(\d{5,8})\b', _normalize_text(text))
    if match:
        return match.group(1)
    
    # Pattern 40: PCSOP prefix (Corporate Services: PCSOP1926060)
    match = re.search(r'\b(PCSOP\d{7,10})\b', _normalize_text(text))
    if match:
        return match.group(1)
    
    # Pattern 41: INV prefix without space (INV1293)
    match = re.search(r'\b(INV\d{4,8})\b', _normalize_text(text))
    if match:
        return match.group(1)
    
    # Pattern 42: Columnar Number header
    for i, line in enumerate(lines[:20]):
        if line.strip() == 'Number':
            for j in range(i+1, min(i+5, len(lines))):
                val = lines[j].strip()
                if re.match(r'^\d{4,8}$', val):
                    return val
    
    # Pattern 43: XX-YY NNNNNN format (Escondido: 53-EC 196155)
    match = re.search(r'\b(\d{2}-[A-Z]{2}\s*\d{6})\b', _normalize_text(text))
    if match:
        return match.group(1).replace(' ', '')
    
    # Pattern 44: TRIP prefix (scale trips: TRIP765317)
    match = re.search(r'\b(TRIP\d{6,10})\b', _normalize_text(text))
    if match:
        return match.group(1)
    
    # Pattern 45: Multi-line Invoice # header (Date on one line, number below)
    for i, line in enumerate(lines[:25]):
        if line.strip() == 'Invoice' and i+2 < len(lines):
            if lines[i+1].strip() == '#':
                # Check next few lines for number
                for j in range(i+2, min(i+6, len(lines))):
                    val = lines[j].strip()
                    if re.match(r'^\d{5,8}$', val):
                        return val
    
    # Pattern 46: Invoice No with alphanumeric prefix (SC106401899)
    match = re.search(r'Invoice\s*No\.?\s*([A-Z]{2}\d{8,12})', _normalize_text(text), re.I)
    if match:
        return match.group(1)
    
    # Pattern 47: "INVOICE NO." header at end of line, value on next lines
    for i, line in enumerate(lines[:25]):
        if line.strip().upper().endswith('INVOICE NO.') or line.strip().upper() == 'INVOICE NO.':
            for j in range(i+1, min(i+5, len(lines))):
                val = lines[j].strip()
                if re.match(r'^\d{5,12}$', val):
                    return val
    
    # Pattern 48: INVOICE followed by number inline (INVOICE 28354)
    match = re.search(r'\bINVOICE\s+(\d{4,8})\b', _normalize_text(text))
    if match:
        return match.group(1)
    
    # Pattern 49: Invoice No. with dash format (169-744)
    match = re.search(r'Invoice\s*No\.?\s*(\d{3}-\d{3,4})', _normalize_text(text), re.I)
    if match:
        return match.group(1)
    
    # Pattern 50: Alphanumeric invoice with prefix (RD11316461)
    match = re.search(r'Invoice\s*No\.?\s*([A-Z]{2}\d{8,10})', _normalize_text(text), re.I)
    if match:
        return match.group(1)
    
    # Pattern 51: Columnar format - INVOICE header followed by number several lines down
    for i, line in enumerate(lines[:20]):
        if line.strip().upper() == 'INVOICE':
            # Look for standalone number in next 6 lines
            for j in range(i+1, min(i+7, len(lines))):
                val = lines[j].strip()
                if re.match(r'^\d{4,8}$', val):
                    return val
    
    # Pattern 52: Account Number as fallback for utility-style bills with clear invoice markers
    if 'AMOUNT DUE' in text.upper():
        match = re.search(r'Account\s*Number\s*(\d{2}-\d{6}-\d{2})', _normalize_text(text), re.I)
        if match:
            return match.group(1).replace('-', '')
    
    # Pattern 53: DUMPSTER RECEIPT with number pattern
    match = re.search(r'DUMPSTER\s*RECEIPT.*?(\d{5}-\d{5})', _normalize_text(text), re.I | re.S)
    if match:
        return match.group(1)
    
    # Pattern 54: Invoice # with 4-digit number
    match = re.search(r'Invoice\s*#\s*(\d{4,5})\b', _normalize_text(text), re.I)
    if match:
        return match.group(1)
    
    # Pattern 55: Reference number with 11+ digits
    match = re.search(r'Reference\s*(\d{11,15})', _normalize_text(text), re.I)
    if match:
        return match.group(1)
    
    # Pattern 56: Account # with parentheses format (61-0475284)
    if 'INVOICE' in text.upper():
        match = re.search(r'Account\s*#[^)]*\((\d{2}-\d{7})', _normalize_text(text), re.I)
        if match:
            return match.group(1)
    
    # Pattern 57: SC prefix (Coastal Waste: SC0000011880)
    match = re.search(r'\b(SC\d{10})\b', _normalize_text(text))
    if match:
        return match.group(1)
    
    # Pattern 58: Bill Number for utility-style bills
    match = re.search(r'Bill\s*Number\s*(\d{6,10})', _normalize_text(text), re.I)
    if match:
        return match.group(1)
    
    # Pattern 59: Customer No. as fallback (7278317)
    if 'INVOICE' in text.upper() or 'BILL' in text.upper():
        match = re.search(r'Customer\s*(?:No\.?|Number)\s*(\d{6,10})', _normalize_text(text), re.I)
        if match:
            return match.group(1)
    
    # Pattern 60: ACCT prefix with alphanumeric (ACCT CM647)
    match = re.search(r'ACCT\s*([A-Z]{2}\d{3,6})', _normalize_text(text))
    if match:
        return match.group(1)
    
    # Pattern 61: INV- prefix (INV-3367)
    match = re.search(r'\b(INV-\d{4,8})\b', _normalize_text(text))
    if match:
        return match.group(1)
    
    # Pattern 62: Month prefix invoice (OCT25-760, NOV25-123)
    match = re.search(r'Invoice\s*No\.?\s*([A-Z]{3}\d{2}-\d{3,6})', _normalize_text(text), re.I)
    if match:
        return match.group(1)
    
    # Pattern 63: Invoice/Receipt # format
    match = re.search(r'Invoice/Receipt\s*#(\d{4,8})', _normalize_text(text), re.I)
    if match:
        return match.group(1)
    
    # Pattern 64: Invoice NNNN standalone at start of line
    match = re.search(r'^Invoice\s+(\d{4,8})\b', _normalize_text(text), re.I | re.M)
    if match:
        return match.group(1)
    
    # Pattern 65: 10-digit invoice number in columnar format
    for i, line in enumerate(lines[:20]):
        if 'Invoice Number' in line or 'INVOICE NUMBER' in line:
            for j in range(i+1, min(i+8, len(lines))):
                val = lines[j].strip()
                if re.match(r'^\d{10}$', val):
                    return val
    
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
    # Normalize text to handle literal \n strings from OCR
    # This ensures all vendor extractors receive consistent text format
    normalized_text = _normalize_text(text)

    # Try vendor-specific extractor first
    if vendor_name in VENDOR_INVOICES:
        result = VENDOR_INVOICES[vendor_name]['extract'](normalized_text)
        if result:
            return result

    # Fallback to generic extraction for all vendors (unconfigured OR when specific fails)
    return _extract_generic_invoice(normalized_text)


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


# ============================================================
# TRANCHE 5: CLOSING THE GAP TO 95%
# ============================================================

def _extract_boro_wide_invoice(text: str) -> Optional[str]:
    """Format: WP + 7 digits
    Examples: WP1059654, WP1076149
    Pattern: Invoice Number header, then WP value on next line
    """
    lines = _split_lines(text)
    for i, line in enumerate(lines[:15]):
        if 'Invoice Number' in line:
            # Check next lines for WP format
            for j in range(i+1, min(i+3, len(lines))):
                val = lines[j].strip()
                if re.match(r'^WP\d{7}$', val):
                    return val
    
    # Fallback direct search
    match = re.search(r'\b(WP\d{7})\b', text)
    if match:
        return match.group(1)
    return None

VENDOR_INVOICES['Boro Wide'] = {
    'format': 'WPNNNNNNN',
    'examples': ['WP1059654', 'WP1076149'],
    'extract': _extract_boro_wide_invoice
}


def _extract_d_crescio_invoice(text: str) -> Optional[str]:
    """Format: MM-DD-YY-NN (date-based)
    Examples: 09-26-25-28, 11-19-25-27
    """
    match = re.search(r'Invoice\s*No\.?\s*(\d{2}-\d{2}-\d{2}-\d{2})', text, re.I)
    if match:
        return match.group(1)
    return None

VENDOR_INVOICES['D Crescio Trucking'] = {
    'format': 'NN-NN-NN-NN',
    'examples': ['09-26-25-28', '11-19-25-27'],
    'extract': _extract_d_crescio_invoice
}


def _extract_community_disposal_invoice(text: str) -> Optional[str]:
    """Format: Invoice NNNNN at start
    Examples: 10871, 11018
    """
    match = re.search(r'^Invoice\s+(\d{5})', _normalize_text(text), re.M)
    if match:
        return match.group(1)
    return None

VENDOR_INVOICES['Community Disposal'] = {
    'format': 'NNNNN',
    'examples': ['10871', '11018'],
    'extract': _extract_community_disposal_invoice
}


def _extract_gulf_coast_containers_invoice(text: str) -> Optional[str]:
    """Format: GC + 10 digits
    Examples: GC0000164335, GC0000165375
    """
    match = re.search(r'\b(GC\d{10})\b', text)
    if match:
        return match.group(1)
    return None

VENDOR_INVOICES['Gulf Coast Containers'] = {
    'format': 'GCNNNNNNNNNN',
    'examples': ['GC0000164335', 'GC0000165375'],
    'extract': _extract_gulf_coast_containers_invoice
}


def _extract_amwaste_invoice(text: str) -> Optional[str]:
    """Format: XX NNNNNNNNNN (state prefix + 10 digits)
    Examples: GA 0000466397, AW 0001536549
    """
    match = re.search(r'INVOICE\s*#:?\s*([A-Z]{2}\s*\d{10})', text, re.I)
    if match:
        return match.group(1).replace(' ', '')
    return None

VENDOR_INVOICES['Amwaste'] = {
    'format': 'XXNNNNNNNNNN',
    'examples': ['GA0000466397', 'AW0001536549'],
    'extract': _extract_amwaste_invoice
}


def _extract_specialty_pallet_invoice(text: str) -> Optional[str]:
    """Format: NNNNNNNV or NNNNN
    Examples: 40191INV, 40502
    """
    lines = _split_lines(text)
    for i, line in enumerate(lines[:15]):
        if line.strip() == 'Invoice #':
            if i+1 < len(lines):
                val = lines[i+1].strip()
                if re.match(r'^\d{5}(INV)?$', val):
                    return val
    match = re.search(r'Invoice\s*#\s*(\d{5}(?:INV)?)', text, re.I)
    if match:
        return match.group(1)
    return None

VENDOR_INVOICES['Specialty Pallet'] = {
    'format': 'NNNNN or NNNNNINV',
    'examples': ['40191INV', '40502'],
    'extract': _extract_specialty_pallet_invoice
}


def _extract_olympic_compactor_invoice(text: str) -> Optional[str]:
    """Format: NNNNNNN-IN
    Examples: 0245139-IN
    """
    match = re.search(r'\b(\d{7}-IN)\b', text)
    if match:
        return match.group(1)
    return None

VENDOR_INVOICES['Olympic Compactor Rentals'] = {
    'format': 'NNNNNNN-IN',
    'examples': ['0245139-IN'],
    'extract': _extract_olympic_compactor_invoice
}


def _extract_jk_trash_invoice(text: str) -> Optional[str]:
    """Format: NXX##### (digit + 2 letters + 5 digits)
    Examples: 5CF02219, 5AF09691
    """
    match = re.search(r'INVOICE#\s*(\d[A-Z]{2}\d{5})', text, re.I)
    if match:
        return match.group(1)
    return None

VENDOR_INVOICES['J&K Trash'] = {
    'format': 'NXXNNNNN',
    'examples': ['5CF02219', '5AF09691'],
    'extract': _extract_jk_trash_invoice
}


def _extract_walker_lake_invoice(text: str) -> Optional[str]:
    """Format: NNNN-N
    Examples: 4090-1
    """
    match = re.search(r'Invoice\s*#\s*(\d{4}-\d)', text, re.I)
    if match:
        return match.group(1)
    return None

VENDOR_INVOICES['Walker Lake Disposal'] = {
    'format': 'NNNN-N',
    'examples': ['4090-1'],
    'extract': _extract_walker_lake_invoice
}


def _extract_mid_valley_disposal_invoice(text: str) -> Optional[str]:
    """Format: 7 digits
    Examples: 3391730, 3343954
    """
    lines = _split_lines(text)
    for i, line in enumerate(lines[:20]):
        if 'Invoice Number' in line:
            # Check nearby lines
            for j in range(max(0, i-2), min(i+3, len(lines))):
                val = lines[j].strip()
                if re.match(r'^\d{7}$', val):
                    return val
    return None

VENDOR_INVOICES['Mid Valley Disposal'] = {
    'format': 'NNNNNNN',
    'examples': ['3391730', '3343954'],
    'extract': _extract_mid_valley_disposal_invoice
}


def _extract_gateway_disposal_invoice(text: str) -> Optional[str]:
    """Format: Statement number or account - no true invoice number
    Uses account number as identifier
    """
    # Gateway uses statements, not invoices - return account as reference
    match = re.search(r'ACCOUNT#\s*(\d{6})', text, re.I)
    if match:
        return match.group(1)
    return None

VENDOR_INVOICES['Gateway Disposal'] = {
    'format': 'NNNNNN (account)',
    'examples': ['718227', '777815'],
    'extract': _extract_gateway_disposal_invoice
}


def _extract_metalpro_invoice(text: str) -> Optional[str]:
    """Format: 6 digits
    Examples: 607875, 607623
    
    OCR shows columnar format with Invoice Number: header
    """
    lines = _split_lines(text)
    
    # Pattern 1: Credit Memo Number or Invoice Number header
    for i, line in enumerate(lines[:20]):
        if 'Invoice Number:' in line or 'Credit Memo Number:' in line:
            # Check same line
            match = re.search(r'(?:Invoice|Credit Memo)\s*Number:\s*(\d{6})', line, re.I)
            if match:
                return match.group(1)
            # Check next lines
            for j in range(i+1, min(i+3, len(lines))):
                val = lines[j].strip()
                if re.match(r'^\d{6}$', val):
                    return val
    
    # Pattern 2: Look for 6-digit standalone in invoice context
    for i, line in enumerate(lines[:10]):
        if 'INVOICE' in line.upper() or 'CREDIT MEMO' in line.upper():
            for j in range(i+1, min(i+5, len(lines))):
                val = lines[j].strip()
                if re.match(r'^\d{6}$', val):
                    return val
    
    return None

VENDOR_INVOICES['Metalpro'] = {
    'format': 'NNNNNN',
    'examples': ['607875', '607623'],
    'extract': _extract_metalpro_invoice
}


def _extract_disposal_management_invoice(text: str) -> Optional[str]:
    """Format: NNXNNNNN (2 digits + letter + 5 digits)
    Examples: 54X25685
    """
    normalized = _normalize_text(text)
    match = re.search(r'INVOICE#\s*(\d{2}[A-Z]\d{5})', normalized, re.I)
    if match:
        return match.group(1)
    return None

VENDOR_INVOICES['Disposal Management'] = {
    'format': 'NNXNNNNN',
    'examples': ['54X25685'],
    'extract': _extract_disposal_management_invoice
}


def _extract_liberty_disposal_invoice(text: str) -> Optional[str]:
    """Format: 10 digits
    Examples: 0000123456
    """
    lines = _split_lines(text)
    for i, line in enumerate(lines[:20]):
        if 'INVOICE' in line.upper():
            for j in range(i+1, min(i+5, len(lines))):
                val = lines[j].strip()
                if re.match(r'^\d{10}$', val):
                    return val
    return None

VENDOR_INVOICES['Liberty Disposal'] = {
    'format': 'NNNNNNNNNN',
    'examples': ['0000123456'],
    'extract': _extract_liberty_disposal_invoice
}


def _extract_heavenly_trash_invoice(text: str) -> Optional[str]:
    """Format: 6-digit
    Examples: 123456
    """
    match = re.search(r'Invoice\s*#?\s*(\d{6})', text, re.I)
    if match:
        return match.group(1)
    return None

VENDOR_INVOICES['Heavenly Trash'] = {
    'format': 'NNNNNN',
    'examples': ['123456'],
    'extract': _extract_heavenly_trash_invoice
}


def _extract_premier_waste_invoice(text: str) -> Optional[str]:
    """Format: INVOICE # header, 5-digit value on next line
    Examples: 34464, 33689
    """
    lines = _split_lines(text)
    for i, line in enumerate(lines[:25]):
        if line.strip() == 'INVOICE #':
            # Get next line
            if i+1 < len(lines):
                val = lines[i+1].strip()
                if re.match(r'^\d{5}$', val):
                    return val
    
    # Fallback
    match = re.search(r'INVOICE\s*#\s*(\d{5})', text, re.I)
    if match:
        return match.group(1)
    return None

VENDOR_INVOICES['Premier Waste'] = {
    'format': 'INV-NNNNN',
    'examples': ['INV-12345'],
    'extract': _extract_premier_waste_invoice
}


def _extract_wg_waste_invoice(text: str) -> Optional[str]:
    """Format: INVOICE #NNNN (4 digits)
    Examples: 5286
    """
    match = re.search(r'INVOICE\s*#\s*(\d{4,6})', text, re.I)
    if match:
        return match.group(1)
    return None

VENDOR_INVOICES['WG Waste'] = {
    'format': 'XXNNNNNNNNNN',
    'examples': ['UK0000449634'],
    'extract': _extract_wg_waste_invoice
}


def _extract_recology_invoice(text: str) -> Optional[str]:
    """Format: 13-digit or various formats
    Examples: 8551003748931
    """
    # 13-digit format
    match = re.search(r'\b(\d{13})\b', text)
    if match:
        return match.group(1)
    # Invoice number inline
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)\s*:?\s*(\d{6,10})', text, re.I)
    if match:
        return match.group(1)
    return None

VENDOR_INVOICES['Recology'] = {
    'format': 'NNNNNNNNNNNNN',
    'examples': ['8551003748931'],
    'extract': _extract_recology_invoice
}


def _extract_arrowaste_invoice(text: str) -> Optional[str]:
    """Format: 6-7 digit
    """
    match = re.search(r'Invoice\s*#?\s*:?\s*(\d{6,7})', text, re.I)
    if match:
        return match.group(1)
    return None

VENDOR_INVOICES['Arrowaste'] = {
    'format': 'NNNNNN',
    'examples': ['123456'],
    'extract': _extract_arrowaste_invoice
}


def _extract_velpen_trucking_invoice(text: str) -> Optional[str]:
    """Format: Various
    """
    match = re.search(r'Invoice\s*#?\s*:?\s*(\d{5,8})', text, re.I)
    if match:
        return match.group(1)
    return None

VENDOR_INVOICES['Velpen Trucking'] = {
    'format': 'NNNNN-NNNNNNNN',
    'examples': ['12345'],
    'extract': _extract_velpen_trucking_invoice
}


def _extract_trash_taxi_invoice(text: str) -> Optional[str]:
    """Format: 6 digit
    Examples: 120842
    """
    match = re.search(r'Invoice\s*#?\s*:?\s*(\d{6})', text, re.I)
    if match:
        return match.group(1)
    return None

VENDOR_INVOICES['Trash Taxi'] = {
    'format': 'NNNNNN',
    'examples': ['120842'],
    'extract': _extract_trash_taxi_invoice
}


def _extract_rdt_inc_invoice(text: str) -> Optional[str]:
    """Format: Various
    """
    match = re.search(r'Invoice\s*#?\s*:?\s*(\d{5,8})', text, re.I)
    if match:
        return match.group(1)
    return None

VENDOR_INVOICES['RDT Inc'] = {
    'format': 'NNNNN',
    'examples': ['12345'],
    'extract': _extract_rdt_inc_invoice
}


def _extract_grizzly_disposal_invoice(text: str) -> Optional[str]:
    """Format: Various
    """
    match = re.search(r'Invoice\s*#?\s*:?\s*(\d{5,8})', text, re.I)
    if match:
        return match.group(1)
    return None

VENDOR_INVOICES['Grizzly Disposal'] = {
    'format': 'NNNNN',
    'examples': ['12345'],
    'extract': _extract_grizzly_disposal_invoice
}


def _extract_pelican_waste_invoice(text: str) -> Optional[str]:
    """Format: Various
    """
    match = re.search(r'Invoice\s*#?\s*:?\s*(\d{5,8})', text, re.I)
    if match:
        return match.group(1)
    return None

VENDOR_INVOICES['Pelican Waste'] = {
    'format': 'NNNNN',
    'examples': ['12345'],
    'extract': _extract_pelican_waste_invoice
}


def _extract_nk_waste_invoice(text: str) -> Optional[str]:
    """Format: Various
    """
    match = re.search(r'Invoice\s*#?\s*:?\s*(\d{5,8})', text, re.I)
    if match:
        return match.group(1)
    return None

VENDOR_INVOICES['NK Waste'] = {
    'format': 'NNNNN',
    'examples': ['12345'],
    'extract': _extract_nk_waste_invoice
}


def _extract_community_waste_invoice(text: str) -> Optional[str]:
    """Format: Various
    """
    match = re.search(r'Invoice\s*#?\s*:?\s*(\d{5,8})', text, re.I)
    if match:
        return match.group(1)
    return None

VENDOR_INVOICES['Community Waste'] = {
    'format': 'NNNNN',
    'examples': ['12345'],
    'extract': _extract_community_waste_invoice
}


def _extract_ryland_environmental_invoice(text: str) -> Optional[str]:
    """Format: Various
    """
    match = re.search(r'Invoice\s*#?\s*:?\s*(\d{5,8})', text, re.I)
    if match:
        return match.group(1)
    return None

VENDOR_INVOICES['Ryland Environmental'] = {
    'format': 'NNNNN',
    'examples': ['12345'],
    'extract': _extract_ryland_environmental_invoice
}


def _extract_blue_diamond_disposal_invoice(text: str) -> Optional[str]:
    """Format: 10-digit with leading zeros
    Examples: 0000907739
    """
    lines = _split_lines(text)
    for i, line in enumerate(lines[:15]):
        if 'INVOICE NO' in line.upper():
            # Check next lines for 10-digit
            for j in range(i+1, min(i+4, len(lines))):
                val = lines[j].strip()
                if re.match(r'^\d{10}$', val):
                    return val
    
    # Fallback
    match = re.search(r'INVOICE\s*NO\.?\s*(\d{10})', text, re.I)
    if match:
        return match.group(1)
    return None

VENDOR_INVOICES['Blue Diamond Disposal'] = {
    'format': 'NNNNN',
    'examples': ['12345'],
    'extract': _extract_blue_diamond_disposal_invoice
}


def _extract_waste_services_llc_invoice(text: str) -> Optional[str]:
    """Format: Various
    """
    match = re.search(r'Invoice\s*#?\s*:?\s*(\d{5,8})', text, re.I)
    if match:
        return match.group(1)
    return None

VENDOR_INVOICES['Waste Services LLC'] = {
    'format': 'NNNNN',
    'examples': ['12345'],
    'extract': _extract_waste_services_llc_invoice
}


# Utility bill vendors - use account number as reference
def _extract_city_of_boise_invoice(text: str) -> Optional[str]:
    """Utility bill - use Account # as identifier"""
    match = re.search(r'Account\s*#:?\s*(\d{15})', text, re.I)
    if match:
        return match.group(1)
    return None

VENDOR_INVOICES['City of Boise'] = {
    'format': 'NNNNNNNNNNNNNNN (account)',
    'examples': ['057576800095407'],
    'extract': _extract_city_of_boise_invoice
}


def _extract_western_disposal_invoice(text: str) -> Optional[str]:
    """Statement - use Account # as identifier"""
    match = re.search(r'Account\s*#\s*(\d{6})', text, re.I)
    if match:
        return match.group(1)
    return None

VENDOR_INVOICES['Western Disposal'] = {
    'format': 'NNNNNN (account)',
    'examples': ['123825', '121004'],
    'extract': _extract_western_disposal_invoice
}


def _extract_lexington_site_services_invoice(text: str) -> Optional[str]:
    """Utility bill - no invoice number"""
    # Try account number
    match = re.search(r'Account\s*Number\s*(\d+)', text, re.I)
    if match:
        return match.group(1)
    return None

VENDOR_INVOICES['Lexington Site Services'] = {
    'format': 'Account Number',
    'examples': ['12345'],
    'extract': _extract_lexington_site_services_invoice
}


def _extract_city_of_jackson_invoice(text: str) -> Optional[str]:
    """Mixed municipal - try customer number"""
    match = re.search(r'(?:CUSTOMER\s*NO\.|Account\s*Number)\s*[:\s]*(\d{6,})', text, re.I)
    if match:
        return match.group(1)
    return None

VENDOR_INVOICES['City of Jackson'] = {
    'format': 'NNNNNNN',
    'examples': ['7310746'],
    'extract': _extract_city_of_jackson_invoice
}


def _extract_dekalb_county_invoice(text: str) -> Optional[str]:
    """Statement Number"""
    match = re.search(r'Statement\s*Number\s*(\d{8})', text, re.I)
    if match:
        return match.group(1)
    return None

VENDOR_INVOICES['DeKalb County'] = {
    'format': 'NNNNNNNN',
    'examples': ['08799200'],
    'extract': _extract_dekalb_county_invoice
}


def _extract_city_of_blackfoot_invoice(text: str) -> Optional[str]:
    """Utility - account number"""
    match = re.search(r'Account\s*(?:Number|#)\s*[:\s]*(\d{6,})', text, re.I)
    if match:
        return match.group(1)
    return None

VENDOR_INVOICES['City of Blackfoot'] = {
    'format': 'Account',
    'examples': ['123456'],
    'extract': _extract_city_of_blackfoot_invoice
}


def _extract_curbside_invoice(text: str) -> Optional[str]:
    """Format: Invoice #NNNN"""
    match = re.search(r'Invoice\s*#\s*(\d{4,6})', text, re.I)
    if match:
        return match.group(1)
    return None

VENDOR_INVOICES['Curbside'] = {
    'format': 'NNNN',
    'examples': ['6493'],
    'extract': _extract_curbside_invoice
}


def _extract_lakeshore_recycling_invoice(text: str) -> Optional[str]:
    """Customer Number based (statement format)"""
    match = re.search(r'Customer\s*Number:\s*([\d.]+)', text, re.I)
    if match:
        return match.group(1)
    return None

VENDOR_INVOICES['Lakeshore Recycling'] = {
    'format': 'NNNN.N',
    'examples': ['5824.9'],
    'extract': _extract_lakeshore_recycling_invoice
}


# ============================================================
# TRANCHE 5B: FIX CONFIGURED VENDOR LOW RATES
# ============================================================

# Override ACES Disposal with better pattern
def _extract_aces_disposal_invoice_v2(text: str) -> Optional[str]:
    """Format: INVOICE #NNNNN or 5-6 digit
    Examples: 55391
    """
    # Skip City of Columbia utility bills
    if 'City of Columbia' in text:
        return None
    
    # ACES format: INVOICE #NNNNN
    match = re.search(r'INVOICE\s*#\s*(\d{5,6})', text, re.I)
    if match:
        return match.group(1)
    
    # Proware format
    match = re.search(r'INVOICE#\s*(\d{5,6})', text, re.I)
    if match:
        return match.group(1)
    
    return None

VENDOR_INVOICES['ACES Disposal']['extract'] = _extract_aces_disposal_invoice_v2


# Override Basin Disposal with better pattern
def _extract_basin_disposal_invoice_v2(text: str) -> Optional[str]:
    """Format: 7 digits
    Examples: 5791285
    """
    # Skip payment receipts
    if 'Payment Successful' in text or 'PAYMENT RECEIPT' in text:
        return None
    
    # Invoice number after Invoice: header
    match = re.search(r'Invoice:\s*(\d{7})', text, re.I)
    if match:
        return match.group(1)
    
    # Or standalone 7-digit near Invoice
    lines = _split_lines(text)
    for i, line in enumerate(lines[:20]):
        if 'Invoice:' in line:
            match = re.search(r'(\d{7})', line)
            if match:
                return match.group(1)
    
    return None

VENDOR_INVOICES['Basin Disposal']['extract'] = _extract_basin_disposal_invoice_v2


# Override Apex Waste - skip payment receipts, handle 12-digit columnar
def _extract_apex_waste_invoice_v2(text: str) -> Optional[str]:
    """Format: 12-digit columnar (headers and values in separate columns)
    Examples: 251030099185
    Skip payment receipts
    """
    if 'PAYMENT RECEIPT' in text.upper():
        return None
    
    lines = _split_lines(text)
    
    # Columnar format: "Invoice #:" header, value 3 lines later
    for i, line in enumerate(lines[:25]):
        if line.strip() == 'Invoice #:':
            # Value is typically 3 lines after header in columnar format
            for j in range(i+1, min(i+5, len(lines))):
                val = lines[j].strip()
                if re.match(r'^\d{12}$', val):
                    return val
    
    # Fallback: inline 12-digit
    match = re.search(r'Invoice\s*#:\s*(\d{12})', text, re.I)
    if match:
        return match.group(1)
    
    return None

VENDOR_INVOICES['Apex Waste']['extract'] = _extract_apex_waste_invoice_v2


# Override American Disposal with multiple format support
def _extract_american_disposal_invoice_v2(text: str) -> Optional[str]:
    """Multiple formats:
    - AMERICAN DISPOSAL (MN): Invoice NNNNNNNNN at line 0
    - American Disposal Systems: Invoice # NNNNN (columnar)
    - American Disposal Services (WC subsidiary): Skip - use WC format
    - All American Disposal: Statements (no invoice #)
    """
    # Skip statements
    if 'All American Disposal' in text and 'Statement' in text:
        return None
    
    # Skip Waste Connections subsidiary
    if 'WASTE CONNECTIONS COMPANY' in text.upper():
        return None
    
    # Format 1: Invoice NNNNNNNNN at start (MN format)
    match = re.search(r'^Invoice\s+(\d{9})', _normalize_text(text), re.M)
    if match:
        return match.group(1)
    
    # Format 2: Invoice # columnar (Systems Inc)
    lines = _split_lines(text)
    for i, line in enumerate(lines[:20]):
        if line.strip() == 'Invoice #':
            # Get value from nearby line
            for j in range(i+1, min(i+4, len(lines))):
                val = lines[j].strip()
                if re.match(r'^\d{5,6}$', val):
                    return val
    
    # Format 3: Invoice # inline
    match = re.search(r'Invoice\s*#\s*(\d{5,6})', text, re.I)
    if match:
        return match.group(1)
    
    return None

VENDOR_INVOICES['American Disposal']['extract'] = _extract_american_disposal_invoice_v2


# Override Wasatch Waste - utility bill, use account
def _extract_wasatch_waste_invoice_v2(text: str) -> Optional[str]:
    """Utility bill format - use account number"""
    match = re.search(r'Account\s*(?:Number|#|Information)\s*[:\s]*(\d+\.?\d*)', text, re.I)
    if match:
        return match.group(1).replace('.', '')
    return None

VENDOR_INVOICES['Wasatch Waste']['extract'] = _extract_wasatch_waste_invoice_v2


# Override Standard Waste - Invoice # NNNNNN format
def _extract_standard_waste_invoice_v2(text: str) -> Optional[str]:
    """Format: Invoice # NNNNNN
    Examples: 552592
    """
    # Scale tickets (rare)
    if 'Weighmaster' in text:
        return None
    
    # Standard Waste invoice format: Invoice # NNNNNN
    match = re.search(r'Invoice\s*#\s*(\d{6})', text, re.I)
    if match:
        return match.group(1)
    
    return None

VENDOR_INVOICES['Standard Waste']['extract'] = _extract_standard_waste_invoice_v2


# County Hauling - Noble Environmental format and WM misdetects
def _extract_county_hauling_invoice_v2(text: str) -> Optional[str]:
    """Multiple formats:
    - Noble Environmental: CH + 7 digits (columnar)
    - WM misdetects: 10-digit
    """
    lines = _split_lines(text)
    
    # Noble Environmental format: INVOICE NO. header, CH value below
    for i, line in enumerate(lines[:20]):
        if line.strip() == 'INVOICE NO.':
            # Check next few lines for CH format
            for j in range(i+1, min(i+6, len(lines))):
                val = lines[j].strip()
                if re.match(r'^CH\d{7}$', val):
                    return val
    
    # WM 10-digit format
    match = re.search(r'INVOICE\s*NUMBER:?\s*(\d{10})', text, re.I)
    if match:
        return match.group(1)
    
    # WM Solutions format
    match = re.search(r'Invoice\s*Number:?\s*(\d{7}-\d{4}-\d)', text, re.I)
    if match:
        return match.group(1)
    
    return None

VENDOR_INVOICES['County Hauling']['extract'] = _extract_county_hauling_invoice_v2


# ============================================================
# TRANCHE 5C: MORE NOT CONFIGURED VENDORS
# ============================================================

def _extract_solid_waste_authority_invoice(text: str) -> Optional[str]:
    """Multiple formats - scale tickets and invoices"""
    lines = _split_lines(text)
    
    # Skip pure scale tickets (TICKET format)
    if 'WEIGHMASTER' in text and 'Invoice' not in text:
        return None
    
    # Invoice format: INVOICE NUMBER header
    for i, line in enumerate(lines[:25]):
        if 'INVOICE NUMBER' in line.upper():
            # Check next lines for numeric value
            for j in range(i+1, min(i+5, len(lines))):
                val = lines[j].strip()
                if re.match(r'^\d{5,10}$', val):
                    return val
    
    return None

VENDOR_INVOICES['Solid Waste Authority'] = {
    'format': 'NNNNNNNNNN',
    'examples': ['12345'],
    'extract': _extract_solid_waste_authority_invoice
}


def _extract_pete_pete_invoice(text: str) -> Optional[str]:
    """Haul tickets - use ticket number or PO"""
    # These are haul tickets without invoice numbers
    # Return None for now
    return None

VENDOR_INVOICES['Pete & Pete'] = {
    'format': 'Haul Ticket',
    'examples': ['N/A'],
    'extract': _extract_pete_pete_invoice
}


def _extract_burrtec_invoice(text: str) -> Optional[str]:
    """Format: N + digits (e.g., N0821067869, N2114817841, N02429340)

    Burrtec invoices start with 'N' followed by 7-10 digits.
    NOTE: Customer Number (account) is separate - 6-10 digit numeric.
    Do not confuse invoice number with account number.
    """
    lines = text.replace('\\n', '\n').split('\n')

    # Pattern 1: Look for Invoice Number header followed by N-prefixed number
    for i, line in enumerate(lines):
        if 'invoice number' in line.lower():
            # Check same line first
            match = re.search(r'\b(N\d{7,10})\b', line)
            if match:
                return match.group(1)
            # Check next few lines
            for j in range(i+1, min(i+5, len(lines))):
                val = lines[j].strip()
                if re.match(r'^N\d{7,10}$', val):
                    return val
                # Skip 'STMT' which is a statement, not invoice
                if val == 'STMT':
                    return None

    # Pattern 2: Direct search for N + digits pattern near 'Invoice'
    match = re.search(r'Invoice\s*(?:Number|No\.?|#)?\s*[:\s]*(N\d{7,10})', text, re.I)
    if match:
        return match.group(1)

    return None

VENDOR_INVOICES['Burrtec'] = {
    'format': 'N + 7-10 digits',
    'examples': ['N0821067869', 'N2114817841', 'N02429340'],
    'extract': _extract_burrtec_invoice
}


# ============================================================
# V6 ADDITIONS - Account Linkage Project (January 2026)
# ============================================================

def _extract_empire_waste_invoice(text: str) -> Optional[str]:
    """Empire Waste - NavuSoft format
    Format: 6-digit at first line (NavuSoft)
    Examples: 228516, 215988
    """
    lines = _split_lines(text)

    # Pattern 1: First line is invoice number
    if lines and re.match(r'^\d{6}$', lines[0].strip()):
        return lines[0].strip()

    # Pattern 2: After INVOICE # header
    for i, line in enumerate(lines[:20]):
        if 'INVOICE #' in line.upper():
            match = re.search(r'INVOICE\s*#:?\s*(\d{6})', line, re.I)
            if match:
                return match.group(1)
            for j in range(i+1, min(i+5, len(lines))):
                val = lines[j].strip()
                if re.match(r'^\d{6}$', val):
                    return val
    return None

VENDOR_INVOICES['Empire Waste'] = {
    'format': 'NNNNNN',
    'examples': ['228516', '215988', '215985'],
    'extract': _extract_empire_waste_invoice
}


def _extract_walters_recycling_invoice(text: str) -> Optional[str]:
    """Walters Recycling
    Format: 10-digit with leading zeros
    Examples: 0009311195, 0009236139
    """
    # Invoice No. at bottom of document
    match = re.search(r'Invoice\s*No\.?\s*[:\s]*(\d{10})', text, re.I)
    if match:
        return match.group(1)
    return None

VENDOR_INVOICES['Walters Recycling'] = {
    'format': 'NNNNNNNNNN',
    'examples': ['0009311195', '0009236139', '0009236137'],
    'extract': _extract_walters_recycling_invoice
}


def _extract_nexus_disposal_invoice(text: str) -> Optional[str]:
    """Nexus Disposal
    Format: 7-digit after INVOICE:
    Examples: 1584373, 1588507
    """
    match = re.search(r'INVOICE[:\s]+(\d{7})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Nexus Disposal'] = {
    'format': 'NNNNNNN',
    'examples': ['1584373', '1588507', '1588527'],
    'extract': _extract_nexus_disposal_invoice
}


def _extract_liberty_waste_invoice(text: str) -> Optional[str]:
    """Liberty Waste Solutions
    Format: 7-digit after INVOICE #
    Examples: 1852022, 1847885
    """
    match = re.search(r'INVOICE\s*#\s*(\d{7})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Liberty Waste'] = {
    'format': 'NNNNNNN',
    'examples': ['1852022', '1847885', '1864006'],
    'extract': _extract_liberty_waste_invoice
}


def _extract_all_american_waste_invoice(text: str) -> Optional[str]:
    """All American Waste
    Format: 10-digit after INVOICE #
    Examples: 0804092643, 0804076500
    """
    match = re.search(r'INVOICE\s*#\s*(\d{10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['All American Waste'] = {
    'format': 'NNNNNNNNNN',
    'examples': ['0804092643', '0804076500', '0804076492'],
    'extract': _extract_all_american_waste_invoice
}


def _extract_troiano_waste_invoice(text: str) -> Optional[str]:
    """Troiano Waste Services
    Format: 10-digit after INVOICE NO (may be on next line)
    Examples: 0000820196, 0000820198
    """
    # Same line
    match = re.search(r'INVOICE\s*NO[:\s]*(\d{10})', text, re.I)
    if match:
        return match.group(1)

    # Next line
    lines = _split_lines(text)
    for i, line in enumerate(lines[:20]):
        if 'INVOICE NO' in line.upper():
            for j in range(i+1, min(i+4, len(lines))):
                val = lines[j].strip()
                if re.match(r'^\d{10}$', val):
                    return val
    return None

VENDOR_INVOICES['Troiano Waste'] = {
    'format': 'NNNNNNNNNN',
    'examples': ['0000820196', '0000820198', '0000820179'],
    'extract': _extract_troiano_waste_invoice
}


def _extract_usa_waste_invoice(text: str) -> Optional[str]:
    """USA Waste & Recycling
    Format: 10-digit after INVOICE #
    Examples: 4202751495, 4202770717
    """
    match = re.search(r'INVOICE\s*#\s*(\d{10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['USA Waste'] = {
    'format': 'NNNNNNNNNN',
    'examples': ['4202751495', '4202770717', '4202770715'],
    'extract': _extract_usa_waste_invoice
}


def _extract_arrowaste_invoice(text: str) -> Optional[str]:
    """Arrowaste
    Format: 7-digit after INVOICE #:
    Examples: 3261462, 3255179
    """
    match = re.search(r'INVOICE\s*#:?\s*(\d{7})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Arrowaste'] = {
    'format': 'NNNNNNN',
    'examples': ['3261462', '3255179', '3234355'],
    'extract': _extract_arrowaste_invoice
}


def _extract_delta_waste_invoice(text: str) -> Optional[str]:
    """Delta Waste Solutions - NavuSoft format
    Format: 5-digit at first line
    Examples: 30289, 30263, 31656
    """
    lines = _split_lines(text)

    # Pattern 1: First line is invoice number
    if lines and re.match(r'^\d{5}$', lines[0].strip()):
        return lines[0].strip()

    # Pattern 2: After INVOICE # header
    for i, line in enumerate(lines[:20]):
        if 'INVOICE #' in line.upper():
            match = re.search(r'INVOICE\s*#:?\s*(\d{5})', line, re.I)
            if match:
                return match.group(1)
            for j in range(i+1, min(i+5, len(lines))):
                val = lines[j].strip()
                if re.match(r'^\d{5}$', val):
                    return val
    return None

VENDOR_INVOICES['Delta Waste'] = {
    'format': 'NNNNN',
    'examples': ['30289', '30263', '31656'],
    'extract': _extract_delta_waste_invoice
}


# ============================================================
# V6 BATCH 2 - Full Gap Closure (January 2026)
# ============================================================

def _extract_fusion_waste_invoice(text: str) -> Optional[str]:
    """Fusion Waste"""
    match = re.search(r'INVOICE\s*NO[:\s]*(\d{10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Fusion Waste'] = {'format': 'NNNNNNNNNN', 'examples': ['0000123207'], 'extract': _extract_fusion_waste_invoice}


def _extract_ware_disposal_invoice(text: str) -> Optional[str]:
    """Ware Disposal - formats: INV# NNNNNNN, Invoice # NNNNNNN"""
    match = re.search(r'(?:Invoice|INV)\s*#\s*(\d{7})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Ware Disposal'] = {'format': 'NNNNNNN', 'examples': ['1925097'], 'extract': _extract_ware_disposal_invoice}


def _extract_harters_invoice(text: str) -> Optional[str]:
    """Harter's"""
    lines = _split_lines(text)
    for i, line in enumerate(lines[:20]):
        if 'Invoice #' in line:
            for j in range(i+1, min(i+4, len(lines))):
                val = lines[j].strip()
                if re.match(r'^\d{7,10}$', val):
                    return val
    return None

VENDOR_INVOICES["Harter's"] = {'format': 'NNNNNNNNNN', 'examples': ['0000615603'], 'extract': _extract_harters_invoice}


def _extract_best_way_disposal_invoice(text: str) -> Optional[str]:
    """Best Way Disposal"""
    match = re.search(r'Invoice\s*Number[:\s]*(\d{7})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Best Way Disposal'] = {'format': 'NNNNNNN', 'examples': ['1828215'], 'extract': _extract_best_way_disposal_invoice}


def _extract_ankeny_sanitation_invoice(text: str) -> Optional[str]:
    """Ankeny Sanitation"""
    match = re.search(r'Invoice\s*#:\s*(\d{7})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Ankeny Sanitation'] = {'format': 'NNNNNNN', 'examples': ['2153768'], 'extract': _extract_ankeny_sanitation_invoice}


def _extract_honolulu_disposal_invoice(text: str) -> Optional[str]:
    """Honolulu Disposal"""
    match = re.search(r'Invoice:\s*(\d{6})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Honolulu Disposal'] = {'format': 'NNNNNN', 'examples': ['863225'], 'extract': _extract_honolulu_disposal_invoice}


def _extract_stevens_disposal_invoice(text: str) -> Optional[str]:
    """Stevens Disposal"""
    lines = _split_lines(text)
    for i, line in enumerate(lines[:20]):
        if 'Invoice #' in line:
            for j in range(i+1, min(i+4, len(lines))):
                val = lines[j].strip()
                if re.match(r'^\d{7}$', val):
                    return val
    return None

VENDOR_INVOICES['Stevens Disposal'] = {'format': 'NNNNNNN', 'examples': ['1095445'], 'extract': _extract_stevens_disposal_invoice}


def _extract_ace_waste_systems_invoice(text: str) -> Optional[str]:
    """Ace Waste Systems"""
    match = re.search(r'Invoice\s*#:\s*(\d{6})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Ace Waste Systems'] = {'format': 'NNNNNN', 'examples': ['494953'], 'extract': _extract_ace_waste_systems_invoice}


def _extract_knighthorst_invoice(text: str) -> Optional[str]:
    """KnightHorst"""
    match = re.search(r'INVOICE\s*#?(\d{6})', text, re.I)
    if match:
        return match.group(1)
    match = re.search(r'#(\d{6})\b', text)
    return match.group(1) if match else None

VENDOR_INVOICES['KnightHorst'] = {'format': 'NNNNNN', 'examples': ['667223'], 'extract': _extract_knighthorst_invoice}


def _extract_eoms_recycling_invoice(text: str) -> Optional[str]:
    """EOMS Recycling"""
    match = re.search(r'Invoice\s+(\d{6})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['EOMS Recycling'] = {'format': 'NNNNNN', 'examples': ['705768'], 'extract': _extract_eoms_recycling_invoice}


def _extract_modern_corporation_invoice(text: str) -> Optional[str]:
    """Modern Corporation"""
    match = re.search(r'Invoice\s+(\d{10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Modern Corporation'] = {'format': 'NNNNNNNNNN', 'examples': ['0016701786'], 'extract': _extract_modern_corporation_invoice}


def _extract_stericycle_invoice(text: str) -> Optional[str]:
    """Stericycle"""
    match = re.search(r'Invoice\s*No\.?\s*(\d{10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Stericycle'] = {'format': 'NNNNNNNNNN', 'examples': ['8012732234'], 'extract': _extract_stericycle_invoice}


def _extract_boren_brothers_invoice(text: str) -> Optional[str]:
    """Boren Brothers"""
    lines = _split_lines(text)
    for i, line in enumerate(lines[:20]):
        if 'INVOICE NO' in line.upper():
            for j in range(i+1, min(i+4, len(lines))):
                val = lines[j].strip()
                if re.match(r'^\d{10}$', val):
                    return val
    return None

VENDOR_INVOICES['Boren Brothers'] = {'format': 'NNNNNNNNNN', 'examples': ['0000741224'], 'extract': _extract_boren_brothers_invoice}


def _extract_vls_environmental_invoice(text: str) -> Optional[str]:
    """VLS Environmental"""
    match = re.search(r'Invoice\s*#:\s*(\d{6})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['VLS Environmental'] = {'format': 'NNNNNN', 'examples': ['277158'], 'extract': _extract_vls_environmental_invoice}


def _extract_smith_creek_invoice(text: str) -> Optional[str]:
    """Smith Creek"""
    lines = _split_lines(text)
    for i, line in enumerate(lines[:20]):
        if 'INVOICE NO' in line.upper():
            for j in range(i+1, min(i+4, len(lines))):
                val = lines[j].strip()
                if re.match(r'^\d{6}$', val):
                    return val
    return None

VENDOR_INVOICES['Smith Creek'] = {'format': 'NNNNNN', 'examples': ['424504'], 'extract': _extract_smith_creek_invoice}


def _extract_live_oak_invoice(text: str) -> Optional[str]:
    """Live Oak"""
    lines = _split_lines(text)
    for i, line in enumerate(lines[:20]):
        if 'INVOICE NO' in line.upper():
            for j in range(i+1, min(i+4, len(lines))):
                val = lines[j].strip()
                if re.match(r'^\d{10}$', val):
                    return val
    return None

VENDOR_INVOICES['Live Oak'] = {'format': 'NNNNNNNNNN', 'examples': ['0002473178'], 'extract': _extract_live_oak_invoice}


def _extract_interstate_waste_invoice(text: str) -> Optional[str]:
    """Interstate Waste"""
    match = re.search(r'Invoice\s*Number:\s*(\d{10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Interstate Waste'] = {'format': 'NNNNNNNNNN', 'examples': ['0011408628'], 'extract': _extract_interstate_waste_invoice}


def _extract_cockey_enterprises_invoice(text: str) -> Optional[str]:
    """Cockey's Enterprises - NavuSoft"""
    lines = _split_lines(text)
    if lines and re.match(r'^\d{7}$', lines[0].strip()):
        return lines[0].strip()
    return None

VENDOR_INVOICES["Cockey's Enterprises"] = {'format': 'NNNNNNN', 'examples': ['3099937'], 'extract': _extract_cockey_enterprises_invoice}


def _extract_zarc_recycling_invoice(text: str) -> Optional[str]:
    """ZARC Recycling"""
    match = re.search(r'Invoice\s*No:\s*([A-Z]{2}-[A-Za-z]+\d{4})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['ZARC Recycling'] = {'format': 'AA-MmmYYYY', 'examples': ['LR-Nov2025'], 'extract': _extract_zarc_recycling_invoice}


def _extract_kmg_hauling_invoice(text: str) -> Optional[str]:
    """KMG Hauling"""
    lines = _split_lines(text)
    for i, line in enumerate(lines[:20]):
        if 'INVOICE NO' in line.upper():
            for j in range(i+1, min(i+4, len(lines))):
                val = lines[j].strip()
                if re.match(r'^\d{10}$', val):
                    return val
    return None

VENDOR_INVOICES['KMG Hauling'] = {'format': 'NNNNNNNNNN', 'examples': ['0000498827'], 'extract': _extract_kmg_hauling_invoice}


def _extract_ssf_scavenger_invoice(text: str) -> Optional[str]:
    """South San Francisco Scavenger"""
    match = re.search(r'Invoice\s*No\.?\s*(\d{10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['South San Francisco Scavenger'] = {'format': 'NNNNNNNNNN', 'examples': ['0001637845'], 'extract': _extract_ssf_scavenger_invoice}


def _extract_flood_brothers_invoice(text: str) -> Optional[str]:
    """Flood Brothers"""
    match = re.search(r'INVOICE\s*NO:\s*(\d{7})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Flood Brothers'] = {'format': 'NNNNNNN', 'examples': ['8182180'], 'extract': _extract_flood_brothers_invoice}


def _extract_valley_vista_invoice(text: str) -> Optional[str]:
    """Valley Vista"""
    match = re.search(r'Invoice\s*#\s*(\d{7})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Valley Vista'] = {'format': 'NNNNNNN', 'examples': ['1925304'], 'extract': _extract_valley_vista_invoice}


def _extract_moore_coal_invoice(text: str) -> Optional[str]:
    """Moore Coal"""
    match = re.search(r'Invoice\s*#?\s*(\d{5})\b', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Moore Coal'] = {'format': 'NNNNN', 'examples': ['75375'], 'extract': _extract_moore_coal_invoice}


def _extract_crr_invoice(text: str) -> Optional[str]:
    """CR&R - 9 digit invoice numbers (e.g., 001581421)

    CR&R invoice format:
    - Account Number: NN-NNNNNNN N (e.g., 22-0113462 2)
    - Invoice Number: 9-digit (e.g., 001581421)

    OCR has columnar layout with headers then values.
    """
    lines = _split_lines(text)

    # Pattern 1: Look for Invoice Number header, then find 9-digit value nearby
    for i, line in enumerate(lines[:25]):
        if 'invoice number' in line.lower():
            # Search next 10 lines for 9-digit number
            for j in range(i+1, min(i+10, len(lines))):
                val = lines[j].strip()
                if re.match(r'^\d{9}$', val):
                    return val
                # Also check inline on same line
                match = re.search(r'\b(\d{9})\b', lines[j])
                if match:
                    return match.group(1)

    # Pattern 2: Direct search near end of document (payment stub)
    match = re.search(r'Invoice\s*Number\s*\n?\s*(\d{9})', _normalize_text(text), re.I)
    if match:
        return match.group(1)

    return None

VENDOR_INVOICES['CR&R'] = {'format': 'NNNNNNNNN (9-digit)', 'examples': ['001581421', '000623808', '000105087'], 'extract': _extract_crr_invoice}


def _extract_mountain_state_waste_invoice(text: str) -> Optional[str]:
    """Mountain State Waste"""
    match = re.search(r'Invoice\s*no\.?:\s*(\d{5})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Mountain State Waste'] = {'format': 'NNNNN', 'examples': ['64975'], 'extract': _extract_mountain_state_waste_invoice}


def _extract_cc_disposal_invoice(text: str) -> Optional[str]:
    """C&C Disposal"""
    match = re.search(r'INVOICE\s*#\s*(\d{6})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['C&C Disposal'] = {'format': 'NNNNNN', 'examples': ['150545'], 'extract': _extract_cc_disposal_invoice}


def _extract_eco_tech_invoice(text: str) -> Optional[str]:
    """Eco-Tech"""
    match = re.search(r'INVOICE#?\s*(\d{7})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Eco-Tech'] = {'format': 'NNNNNNN', 'examples': ['1714692'], 'extract': _extract_eco_tech_invoice}


def _extract_atlantic_waste_invoice(text: str) -> Optional[str]:
    """Atlantic Waste"""
    match = re.search(r'Invoice\s*Number\s*(\d{7})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Atlantic Waste'] = {'format': 'NNNNNNN', 'examples': ['1044333'], 'extract': _extract_atlantic_waste_invoice}


def _extract_jlt_trucking_invoice(text: str) -> Optional[str]:
    """JLT Trucking"""
    lines = _split_lines(text)
    for i, line in enumerate(lines[:20]):
        if 'Invoice #' in line:
            for j in range(i+1, min(i+4, len(lines))):
                val = lines[j].strip()
                if re.match(r'^\d{6}$', val):
                    return val
    return None

VENDOR_INVOICES['JLT Trucking'] = {'format': 'NNNNNN', 'examples': ['131449'], 'extract': _extract_jlt_trucking_invoice}


def _extract_huntsville_hauling_invoice(text: str) -> Optional[str]:
    """Huntsville Hauling"""
    match = re.search(r'INVOICE\s*NO\.?\s*(\d+[A-Z]\d+)', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Huntsville Hauling'] = {'format': 'NNNNNNNNSNNNN', 'examples': ['103576353S420'], 'extract': _extract_huntsville_hauling_invoice}


def _extract_schaap_sanitation_invoice(text: str) -> Optional[str]:
    """Schaap Sanitation"""
    match = re.search(r'INVOICE\s*NO\.?\s*(\d+[A-Z]\d+)', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Schaap Sanitation'] = {'format': 'NNNNNNNTNNNN', 'examples': ['4323998T061'], 'extract': _extract_schaap_sanitation_invoice}


def _extract_cooks_wastepaper_invoice(text: str) -> Optional[str]:
    """Cooks Wastepaper"""
    match = re.search(r'INVOICE\s*NO\.?\s*(\d+[A-Z]\d+)', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Cooks Wastepaper'] = {'format': 'NNNNNNNTNNNN', 'examples': ['4492483T032'], 'extract': _extract_cooks_wastepaper_invoice}


def _extract_abc_waste_invoice(text: str) -> Optional[str]:
    """ABC Waste"""
    match = re.search(r'INVOICE\s*#:?\s*(\d{5,6})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['ABC Waste'] = {'format': 'NNNNN', 'examples': ['38832'], 'extract': _extract_abc_waste_invoice}


def _extract_my_trash_invoice(text: str) -> Optional[str]:
    """My Trash"""
    match = re.search(r'Transaction\s*No\s*.*?(\d{10})', text, re.I | re.S)
    return match.group(1) if match else None

VENDOR_INVOICES['My Trash'] = {'format': 'NNNNNNNNNN', 'examples': ['9024883197'], 'extract': _extract_my_trash_invoice}


def _extract_renewable_resources_invoice(text: str) -> Optional[str]:
    """Renewable Resources"""
    match = re.search(r'INVOICE\s*NO\.?\s*(\d+[A-Z]\d+)', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Renewable Resources'] = {'format': 'NNNNNNVNNN', 'examples': ['4360946V120'], 'extract': _extract_renewable_resources_invoice}


# ============================================================
# NEW VENDORS - JANUARY 2026 BATCH (Automated Analysis)
# ============================================================

def _extract_stryker_environmental_invoice(text: str) -> Optional[str]:
    """Stryker Environmental - Format: Invoice no.: NNNNN
    Examples: 64770
    """
    match = re.search(r'Invoice\s*no\.?:?\s*(\d{5})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Stryker Environmental'] = {'format': 'NNNNN', 'examples': ['64770'], 'extract': _extract_stryker_environmental_invoice}


def _extract_wompost_invoice(text: str) -> Optional[str]:
    """Wompost/Total Recycling - Format: Invoice #NNNNN
    Examples: 18616
    """
    match = re.search(r'Invoice\s*#(\d{5})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Wompost'] = {'format': 'NNNNN', 'examples': ['18616'], 'extract': _extract_wompost_invoice}


def _extract_community_disposal_invoice(text: str) -> Optional[str]:
    """Community Disposal - Format: Invoice NNNN
    Examples: 9384
    """
    match = re.search(r'^Invoice\s+(\d{4,5})', _normalize_text(text), re.M | re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Community Disposal'] = {'format': 'NNNN', 'examples': ['9384'], 'extract': _extract_community_disposal_invoice}


def _extract_curbside_invoice(text: str) -> Optional[str]:
    """Curbside Inc - Format: Invoice #NNNN
    Examples: 7262
    """
    match = re.search(r'Invoice\s*#(\d{4,5})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Curbside'] = {'format': 'NNNN', 'examples': ['7262'], 'extract': _extract_curbside_invoice}


def _extract_waste_away_invoice(text: str) -> Optional[str]:
    """Himco Waste-Away - Format: Invoice Number NNNNNNNNNN
    Examples: 0035092576
    """
    match = re.search(r'Invoice\s*Number\s*\\n?(\d{10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Waste Away'] = {'format': 'NNNNNNNNNN', 'examples': ['0035092576'], 'extract': _extract_waste_away_invoice}


def _extract_blue_hills_environmental_invoice(text: str) -> Optional[str]:
    """Blue Hills Environmental - Format: Invoice # NNNNNNNNNNN
    Examples: 10872737560
    """
    match = re.search(r'Invoice\s*#\s*\\n?(\d{10,11})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Blue Hills Environmental'] = {'format': 'NNNNNNNNNNN', 'examples': ['10872737560'], 'extract': _extract_blue_hills_environmental_invoice}


def _extract_trident_waste_invoice(text: str) -> Optional[str]:
    """Trident Waste - Format: Invoice # NNNNNN
    Examples: 640605
    """
    match = re.search(r'Invoice\s*#\s*\\n?(\d{6})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Trident Waste'] = {'format': 'NNNNNN', 'examples': ['640605'], 'extract': _extract_trident_waste_invoice}


def _extract_west_central_sanitation_invoice(text: str) -> Optional[str]:
    """West Central Sanitation - Format: Invoice Number NNNNNNNN
    Examples: 13617241
    """
    match = re.search(r'Invoice\s*Number\s*\\n?(\d{8})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['West Central Sanitation'] = {'format': 'NNNNNNNN', 'examples': ['13617241'], 'extract': _extract_west_central_sanitation_invoice}


def _extract_tk_trash_invoice(text: str) -> Optional[str]:
    """Trash Kans - Format: INVOICE #: NNNNNNN
    Examples: 9393652
    """
    match = re.search(r'INVOICE\s*#:?\s*(\d{7})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['TK Trash'] = {'format': 'NNNNNNN', 'examples': ['9393652'], 'extract': _extract_tk_trash_invoice}


def _extract_florida_express_waste_invoice(text: str) -> Optional[str]:
    """Florida Express Waste - Format: INVOICE # NNNNNNN
    Examples: 1381108
    """
    match = re.search(r'INVOICE\s*#\s*(\d{7})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Florida Express Waste'] = {'format': 'NNNNNNN', 'examples': ['1381108'], 'extract': _extract_florida_express_waste_invoice}


def _extract_abc_disposal_systems_invoice(text: str) -> Optional[str]:
    """ABC Disposal Systems - Format: Invoice # NNNNNNN
    Examples: 1107239
    """
    match = re.search(r'Invoice\s*#\s*\\n?(\d{7})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['ABC Disposal Systems'] = {'format': 'NNNNNNN', 'examples': ['1107239'], 'extract': _extract_abc_disposal_systems_invoice}


def _extract_heiberg_garbage_invoice(text: str) -> Optional[str]:
    """Heiberg Garbage - no separate invoice, use account"""
    match = re.search(r'Account\s*Number\s*(\d{6})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Heiberg Garbage'] = {'format': 'NNNNNN (account)', 'examples': ['137851'], 'extract': _extract_heiberg_garbage_invoice}


def _extract_cards_recycling_invoice(text: str) -> Optional[str]:
    """Cards Recycling - Format: Invoice # NNNNNNN
    Examples: 1382844
    """
    match = re.search(r'Invoice\s*#\s*\\n?(\d{7})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Cards Recycling'] = {'format': 'NNNNNNN', 'examples': ['1382844'], 'extract': _extract_cards_recycling_invoice}


def _extract_black_hawk_waste_invoice(text: str) -> Optional[str]:
    """Black Hawk Waste - Format: Invoice # NNNNNNN
    Examples: 1382844
    """
    match = re.search(r'Invoice\s*#\s*\\n?(\d{7})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Black Hawk Waste'] = {'format': 'NNNNNNN', 'examples': ['1382844'], 'extract': _extract_black_hawk_waste_invoice}


def _extract_wall_recycling_invoice(text: str) -> Optional[str]:
    """Wall Recycling - Format: Invoice # NNNNNNN
    """
    match = re.search(r'Invoice\s*#\s*\\n?(\d{7})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Wall Recycling'] = {'format': 'NNNNNNN', 'examples': ['1234567'], 'extract': _extract_wall_recycling_invoice}


def _extract_western_elite_invoice(text: str) -> Optional[str]:
    """Western Elite - Format: Invoice NNNNNN
    """
    match = re.search(r'Invoice\s*:?\s*(\d{6})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Western Elite'] = {'format': 'NNNNNN', 'examples': ['123456'], 'extract': _extract_western_elite_invoice}


def _extract_orlando_waste_paper_invoice(text: str) -> Optional[str]:
    """Orlando Waste Paper - Format: INVOICE# NNXNNNNN
    Examples: 58C10267
    """
    match = re.search(r'INVOICE#\s*(\d{2}[A-Z]\d{5})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Orlando Waste Paper'] = {'format': 'NNXNNNNN', 'examples': ['58C10267'], 'extract': _extract_orlando_waste_paper_invoice}


def _extract_county_waste_systems_invoice(text: str) -> Optional[str]:
    """County Waste Systems - Format: Invoice # NNNNNNN
    """
    match = re.search(r'Invoice\s*#\s*\\n?(\d{7})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['County Waste Systems'] = {'format': 'NNNNNNN', 'examples': ['1234567'], 'extract': _extract_county_waste_systems_invoice}


def _extract_sonnys_solid_waste_invoice(text: str) -> Optional[str]:
    """Sonny's Solid Waste - Format: Invoice # NNNNN
    """
    match = re.search(r'Invoice\s*#\s*(\d{5,6})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES["Sonny's Solid Waste"] = {'format': 'NNNNN', 'examples': ['12345'], 'extract': _extract_sonnys_solid_waste_invoice}


def _extract_indiana_waste_invoice(text: str) -> Optional[str]:
    """Indiana Waste - Format: INVOICE# NNXNNNNN
    """
    match = re.search(r'INVOICE#\s*(\d{2}[A-Z]\d{5})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Indiana Waste'] = {'format': 'NNXNNNNN', 'examples': ['12X12345'], 'extract': _extract_indiana_waste_invoice}


def _extract_west_oahu_aggregate_invoice(text: str) -> Optional[str]:
    """West Oahu Aggregate - Format: Invoice # NNNNNNN
    """
    match = re.search(r'Invoice\s*#\s*(\d{6,7})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['West Oahu Aggregate'] = {'format': 'NNNNNNN', 'examples': ['1234567'], 'extract': _extract_west_oahu_aggregate_invoice}


def _extract_northern_waste_invoice(text: str) -> Optional[str]:
    """Northern Waste - Format: Invoice # NNNNNNN
    """
    match = re.search(r'Invoice\s*#\s*(\d{6,7})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Northern Waste'] = {'format': 'NNNNNNN', 'examples': ['1234567'], 'extract': _extract_northern_waste_invoice}


def _extract_south_shore_disposal_invoice(text: str) -> Optional[str]:
    """South Shore Disposal - Format: Invoice # NNNNNN
    """
    match = re.search(r'Invoice\s*#\s*(\d{6})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['South Shore Disposal'] = {'format': 'NNNNNN', 'examples': ['123456'], 'extract': _extract_south_shore_disposal_invoice}


def _extract_cards_ks_invoice(text: str) -> Optional[str]:
    """Cards KS - Format: Invoice # NNNNNNN
    """
    match = re.search(r'Invoice\s*#\s*\\n?(\d{7})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Cards KS'] = {'format': 'NNNNNNN', 'examples': ['1234567'], 'extract': _extract_cards_ks_invoice}


def _extract_community_waste_disposal_invoice(text: str) -> Optional[str]:
    """Community Waste Disposal - Format: Invoice Number NNNNNN
    Examples: 177250
    """
    match = re.search(r'Invoice\s*Number\s*\\n?(\d{6})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Community Waste Disposal'] = {'format': 'NNNNNN', 'examples': ['177250'], 'extract': _extract_community_waste_disposal_invoice}


def _extract_city_waste_invoice(text: str) -> Optional[str]:
    """City Waste/Coastal Compaction - Format: Invoice #: NNNNN
    Examples: 41459
    """
    match = re.search(r'Invoice\s*#:?\s*(\d{5})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['City Waste'] = {'format': 'NNNNN', 'examples': ['41459'], 'extract': _extract_city_waste_invoice}


def _extract_redgate_disposal_invoice(text: str) -> Optional[str]:
    """Redgate Disposal - Format: Invoice # NNNNNN
    Examples: 137933
    """
    match = re.search(r'Invoice\s*#\s*\\n?(\d{6})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Redgate Disposal'] = {'format': 'NNNNNN', 'examples': ['137933'], 'extract': _extract_redgate_disposal_invoice}


def _extract_walker_lake_disposal_invoice(text: str) -> Optional[str]:
    """Walker Lake Disposal - Format: Invoice no.: W-NNNN-NNN
    Examples: W-4431-103
    """
    match = re.search(r'Invoice\s*no\.?:?\s*(W-\d{4}-\d{3})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Walker Lake Disposal'] = {'format': 'W-NNNN-NNN', 'examples': ['W-4431-103'], 'extract': _extract_walker_lake_disposal_invoice}


def _extract_modern_recycling_invoice(text: str) -> Optional[str]:
    """Modern Recycling - Format: Invoice Number: NNNNNNNN
    Examples: 14478531
    """
    match = re.search(r'Invoice\s*(?:Number|#):?\s*(\d{8})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Modern Recycling'] = {'format': 'NNNNNNNN', 'examples': ['14478531'], 'extract': _extract_modern_recycling_invoice}


def _extract_ohio_valley_waste_invoice(text: str) -> Optional[str]:
    """Ohio Valley Waste - Format: Invoice Number: NNNNNN
    Examples: 740967
    """
    match = re.search(r'Invoice\s*Number:?\s*(\d{6})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Ohio Valley Waste'] = {'format': 'NNNNNN', 'examples': ['740967'], 'extract': _extract_ohio_valley_waste_invoice}


def _extract_vogel_disposal_invoice(text: str) -> Optional[str]:
    """Vogel Disposal - Format: Invoice Number: NNNNNNN
    Examples: 2389098
    """
    match = re.search(r'Invoice\s*Number:?\s*(\d{7})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Vogel Disposal'] = {'format': 'NNNNNNN', 'examples': ['2389098'], 'extract': _extract_vogel_disposal_invoice}


def _extract_conex_recycling_invoice(text: str) -> Optional[str]:
    """Conex Recycling - Format: INVOICE NO. NNNNNNNN
    Examples: 02250188
    """
    match = re.search(r'INVOICE\s*NO\.?\s*\\n?(\d{8})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Conex Recycling'] = {'format': 'NNNNNNNN', 'examples': ['02250188'], 'extract': _extract_conex_recycling_invoice}


def _extract_all_metals_recycling_invoice(text: str) -> Optional[str]:
    """All Metals Recycling - Format: Invoice # NNNNN
    Examples: 17499
    """
    match = re.search(r'Invoice\s*#\s*\\n?(\d{5})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['All Metals Recycling'] = {'format': 'NNNNN', 'examples': ['17499'], 'extract': _extract_all_metals_recycling_invoice}


def _extract_corporate_services_consultants_invoice(text: str) -> Optional[str]:
    """Corporate Services Consultants - Format: Invoice XXXXXXXXXX
    Examples: PCSOP1954311
    """
    match = re.search(r'^Invoice\s*\\n([A-Z0-9]+)', _normalize_text(text), re.M | re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Corporate Services Consultants'] = {'format': 'XXXXXXXXXXXX', 'examples': ['PCSOP1954311'], 'extract': _extract_corporate_services_consultants_invoice}


def _extract_clean_slate_invoice(text: str) -> Optional[str]:
    """Clean Slate - Format: Invoice #: NNNNN
    Examples: 10335
    """
    match = re.search(r'Invoice\s*#:?\s*(\d{5})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Clean Slate'] = {'format': 'NNNNN', 'examples': ['10335'], 'extract': _extract_clean_slate_invoice}


def _extract_city_of_tucson_invoice(text: str) -> Optional[str]:
    """City of Tucson - Uses account number as reference"""
    match = re.search(r'ACCOUNT\s*NUMBER\s*\\n?(\d{7}-\d{6})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['City of Tucson'] = {'format': 'NNNNNNN-NNNNNN (account)', 'examples': ['1679429-206512'], 'extract': _extract_city_of_tucson_invoice}

# ============================================================
# AUTO-GENERATED EXTRACTORS FOR MISSING VENDORS
# ============================================================

def _extract_debris_to_green_invoice(text: str) -> Optional[str]:
    """Debris to Green invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Debris to Green'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_debris_to_green_invoice}

def _extract_western_kane_county_invoice(text: str) -> Optional[str]:
    """Western Kane County invoice extractor"""
    match = re.search(r'Invoice\s*#:?\s*(\d{4,6})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Western Kane County'] = {'format': 'NNNNN', 'examples': ['39240'], 'extract': _extract_western_kane_county_invoice}

def _extract_panzarella_waste_invoice(text: str) -> Optional[str]:
    """Panzarella Waste invoice extractor"""
    match = re.search(r'Invoice\s*#:?\s*(\d{5,7})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Panzarella Waste'] = {'format': 'NNNNNN', 'examples': ['384585'], 'extract': _extract_panzarella_waste_invoice}

def _extract_sunrise_sanitation_service_invoice(text: str) -> Optional[str]:
    """Sunrise Sanitation Service invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Sunrise Sanitation Service'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_sunrise_sanitation_service_invoice}

def _extract_ozark_disposal_invoice(text: str) -> Optional[str]:
    """Ozark Disposal invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Ozark Disposal'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_ozark_disposal_invoice}

def _extract_howard_disposal_invoice(text: str) -> Optional[str]:
    """Howard Disposal invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Howard Disposal'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_howard_disposal_invoice}

def _extract_midwest_paper_invoice(text: str) -> Optional[str]:
    """Midwest Paper invoice extractor"""
    match = re.search(r'Invoice\s*No\.?:?\s*(\d{9,11})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Midwest Paper'] = {'format': 'NNNNNNNNNN', 'examples': ['0000143850'], 'extract': _extract_midwest_paper_invoice}

def _extract_c_d_disposal_invoice(text: str) -> Optional[str]:
    """C & D Disposal invoice extractor"""
    match = re.search(r'Invoice\s*Number:?\s*(\d{8,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['C & D Disposal'] = {'format': 'NNNNNNNNN', 'examples': ['000696117'], 'extract': _extract_c_d_disposal_invoice}

def _extract_first_piedmont_invoice(text: str) -> Optional[str]:
    """First Piedmont invoice extractor"""
    match = re.search(r'Invoice\s*No\.?:?\s*(\d{6,8})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['First Piedmont'] = {'format': 'NNNNNNN', 'examples': ['7774603'], 'extract': _extract_first_piedmont_invoice}

def _extract_marick_s_waste_disposal_invoice(text: str) -> Optional[str]:
    """Marick's Waste Disposal invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Marick\'s Waste Disposal'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_marick_s_waste_disposal_invoice}

def _extract_rich_county_invoice(text: str) -> Optional[str]:
    """Rich County invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Rich County'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_rich_county_invoice}

def _extract_j_t_environmental_invoice(text: str) -> Optional[str]:
    """J&T Environmental invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['J&T Environmental'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_j_t_environmental_invoice}

def _extract_pennohio_invoice(text: str) -> Optional[str]:
    """Pennohio invoice extractor"""
    match = re.search(r'Invoice\s*No\.?:?\s*(\d{4,6})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Pennohio'] = {'format': 'NNNNN', 'examples': ['47709'], 'extract': _extract_pennohio_invoice}

def _extract_pacific_waste_invoice(text: str) -> Optional[str]:
    """Pacific Waste invoice extractor"""
    match = re.search(r'INV[-\s]?(\d{4,6})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Pacific Waste'] = {'format': 'INV-NNNNN', 'examples': ['30419'], 'extract': _extract_pacific_waste_invoice}

def _extract_pop_and_son_trucking_invoice(text: str) -> Optional[str]:
    """Pop and Son Trucking invoice extractor"""
    match = re.search(r'Invoice\s*#:?\s*(\d{5,7})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Pop and Son Trucking'] = {'format': 'NNNNNN', 'examples': ['000645'], 'extract': _extract_pop_and_son_trucking_invoice}

def _extract_rocky_ridge_invoice(text: str) -> Optional[str]:
    """Rocky Ridge invoice extractor"""
    match = re.search(r'Invoice\s*#:?\s*(\d{5,7})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Rocky Ridge'] = {'format': 'NNNNNN', 'examples': ['117266'], 'extract': _extract_rocky_ridge_invoice}

def _extract_cwpm_invoice(text: str) -> Optional[str]:
    """CWPM invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['CWPM'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_cwpm_invoice}

def _extract_at_disposal_invoice(text: str) -> Optional[str]:
    """AT Disposal invoice extractor"""
    match = re.search(r'Invoice\s*#:?\s*(\d{5,7})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['AT Disposal'] = {'format': 'NNNNNN', 'examples': ['222691'], 'extract': _extract_at_disposal_invoice}

def _extract_waste_pro_oregon_invoice(text: str) -> Optional[str]:
    """Waste Pro Oregon invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Waste Pro Oregon'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_waste_pro_oregon_invoice}

def _extract_city_of_lompoc_invoice(text: str) -> Optional[str]:
    """City of Lompoc invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['City of Lompoc'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_city_of_lompoc_invoice}

def _extract_amber_disposal_invoice(text: str) -> Optional[str]:
    """Amber Disposal invoice extractor"""
    match = re.search(r'Invoice\s*#:?\s*(\d{9,11})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Amber Disposal'] = {'format': 'NNNNNNNNNN', 'examples': ['2503254531'], 'extract': _extract_amber_disposal_invoice}

def _extract_mission_trail_waste_invoice(text: str) -> Optional[str]:
    """Mission Trail Waste invoice extractor"""
    match = re.search(r'Invoice\s*#:?\s*(\d{9,11})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Mission Trail Waste'] = {'format': 'NNNNNNNNNN', 'examples': ['0000707071'], 'extract': _extract_mission_trail_waste_invoice}

def _extract_miller_and_sons_disposal_invoice(text: str) -> Optional[str]:
    """Miller and Sons Disposal invoice extractor"""
    match = re.search(r'Invoice\s*No\.?:?\s*(\d{5,7})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Miller and Sons Disposal'] = {'format': 'NNNNNN', 'examples': ['101558'], 'extract': _extract_miller_and_sons_disposal_invoice}

def _extract_goode_companies_invoice(text: str) -> Optional[str]:
    """Goode Companies invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Goode Companies'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_goode_companies_invoice}

def _extract_redbox_invoice(text: str) -> Optional[str]:
    """Redbox+ invoice extractor"""
    match = re.search(r'Invoice\s*No\.?:?\s*(\d{9,11})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Redbox+'] = {'format': 'NNNNNNNNNN', 'examples': ['8035004081'], 'extract': _extract_redbox_invoice}

def _extract_sanitation_services_invoice(text: str) -> Optional[str]:
    """Sanitation Services invoice extractor"""
    match = re.search(r'Invoice\s*#:?\s*(\d{9,11})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Sanitation Services'] = {'format': 'NNNNNNNNNN', 'examples': ['0000024615'], 'extract': _extract_sanitation_services_invoice}

def _extract_idaho_falls_utilities_invoice(text: str) -> Optional[str]:
    """Idaho Falls Utilities invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Idaho Falls Utilities'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_idaho_falls_utilities_invoice}

def _extract_norland_environmental_invoice(text: str) -> Optional[str]:
    """Norland Environmental invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Norland Environmental'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_norland_environmental_invoice}

def _extract_lawrence_waste_invoice(text: str) -> Optional[str]:
    """Lawrence Waste invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Lawrence Waste'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_lawrence_waste_invoice}

def _extract_bliss_environmental_invoice(text: str) -> Optional[str]:
    """Bliss Environmental invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Bliss Environmental'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_bliss_environmental_invoice}

def _extract_darob_invoice(text: str) -> Optional[str]:
    """Darob invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Darob'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_darob_invoice}

def _extract_marion_county_fiscal_court_invoice(text: str) -> Optional[str]:
    """Marion County Fiscal Court invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Marion County Fiscal Court'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_marion_county_fiscal_court_invoice}

def _extract_cook_maintenance_invoice(text: str) -> Optional[str]:
    """Cook Maintenance invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Cook Maintenance'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_cook_maintenance_invoice}

def _extract_updike_industries_invoice(text: str) -> Optional[str]:
    """Updike Industries invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Updike Industries'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_updike_industries_invoice}

def _extract_valley_sanitation_llc_invoice(text: str) -> Optional[str]:
    """Valley Sanitation LLC invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Valley Sanitation LLC'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_valley_sanitation_llc_invoice}

def _extract_miami_dade_dswm_invoice(text: str) -> Optional[str]:
    """Miami-Dade DSWM invoice extractor"""
    match = re.search(r'Invoice\s*Number:?\s*(\d{5,7})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Miami-Dade DSWM'] = {'format': 'NNNNNN', 'examples': ['620291'], 'extract': _extract_miami_dade_dswm_invoice}

def _extract_whitecap_waste_invoice(text: str) -> Optional[str]:
    """Whitecap Waste invoice extractor"""
    match = re.search(r'Invoice\s*#:?\s*(\d{6,8})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Whitecap Waste'] = {'format': 'NNNNNNN', 'examples': ['1856223'], 'extract': _extract_whitecap_waste_invoice}

def _extract_seadrunar_recycling_invoice(text: str) -> Optional[str]:
    """Seadrunar Recycling invoice extractor"""
    match = re.search(r'Invoice\s*Number:?\s*(\d{5,7})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Seadrunar Recycling'] = {'format': 'NNNNNN', 'examples': ['276863'], 'extract': _extract_seadrunar_recycling_invoice}

def _extract_dunham_invoice(text: str) -> Optional[str]:
    """Dunham invoice extractor"""
    match = re.search(r'Invoice\s*#:?\s*(\d{4,6})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Dunham'] = {'format': 'NNNNN', 'examples': ['70884'], 'extract': _extract_dunham_invoice}

def _extract_fiber_services_invoice(text: str) -> Optional[str]:
    """Fiber Services invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Fiber Services'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_fiber_services_invoice}

def _extract_industrial_services_lincoln_invoice(text: str) -> Optional[str]:
    """Industrial Services Lincoln invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Industrial Services Lincoln'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_industrial_services_lincoln_invoice}

def _extract_bridge_city_sanitation_invoice(text: str) -> Optional[str]:
    """Bridge City Sanitation invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Bridge City Sanitation'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_bridge_city_sanitation_invoice}

def _extract_green_planet_21_invoice(text: str) -> Optional[str]:
    """Green Planet 21 invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Green Planet 21'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_green_planet_21_invoice}

def _extract_roll_off_systems_invoice(text: str) -> Optional[str]:
    """Roll Off Systems invoice extractor"""
    match = re.search(r'Invoice\s*#:?\s*(\d{9,11})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Roll Off Systems'] = {'format': 'NNNNNNNNNN', 'examples': ['0003815048'], 'extract': _extract_roll_off_systems_invoice}

def _extract_tfc_recycling_invoice(text: str) -> Optional[str]:
    """TFC Recycling invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['TFC Recycling'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_tfc_recycling_invoice}

def _extract_river_parish_disposal_invoice(text: str) -> Optional[str]:
    """River Parish Disposal invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['River Parish Disposal'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_river_parish_disposal_invoice}

def _extract_taylor_sons_invoice(text: str) -> Optional[str]:
    """Taylor & Sons invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Taylor & Sons'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_taylor_sons_invoice}

def _extract_south_tahoe_refuse_invoice(text: str) -> Optional[str]:
    """South Tahoe Refuse invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['South Tahoe Refuse'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_south_tahoe_refuse_invoice}

def _extract_city_of_sallisaw_invoice(text: str) -> Optional[str]:
    """City of Sallisaw invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['City of Sallisaw'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_city_of_sallisaw_invoice}

def _extract_lincoln_county_solid_waste_invoice(text: str) -> Optional[str]:
    """Lincoln County Solid Waste invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Lincoln County Solid Waste'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_lincoln_county_solid_waste_invoice}

def _extract_crp_sanitation_invoice(text: str) -> Optional[str]:
    """CRP Sanitation invoice extractor"""
    match = re.search(r'Invoice\s*No\.?:?\s*(\d{9,11})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['CRP Sanitation'] = {'format': 'NNNNNNNNNN', 'examples': ['0000780304'], 'extract': _extract_crp_sanitation_invoice}

def _extract_greenbrier_valley_solid_waste_invoice(text: str) -> Optional[str]:
    """Greenbrier Valley Solid Waste invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Greenbrier Valley Solid Waste'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_greenbrier_valley_solid_waste_invoice}

def _extract_weaver_s_sanitation_invoice(text: str) -> Optional[str]:
    """Weaver's Sanitation invoice extractor"""
    match = re.search(r'Invoice\s*No\.?:?\s*(\d{9,11})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Weaver\'s Sanitation'] = {'format': 'NNNNNNNNNN', 'examples': ['0000703776'], 'extract': _extract_weaver_s_sanitation_invoice}

def _extract_florida_waste_solutions_invoice(text: str) -> Optional[str]:
    """Florida Waste Solutions invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Florida Waste Solutions'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_florida_waste_solutions_invoice}

def _extract_butler_disposal_systems_invoice(text: str) -> Optional[str]:
    """Butler Disposal Systems invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Butler Disposal Systems'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_butler_disposal_systems_invoice}

def _extract_akat_scrap_metal_invoice(text: str) -> Optional[str]:
    """Akat Scrap Metal invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Akat Scrap Metal'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_akat_scrap_metal_invoice}

def _extract_mike_s_rubbish_invoice(text: str) -> Optional[str]:
    """Mike's Rubbish invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Mike\'s Rubbish'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_mike_s_rubbish_invoice}

def _extract_jim_s_sanitation_invoice(text: str) -> Optional[str]:
    """Jim's Sanitation invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Jim\'s Sanitation'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_jim_s_sanitation_invoice}

def _extract_city_of_pembroke_pines_invoice(text: str) -> Optional[str]:
    """City of Pembroke Pines invoice extractor"""
    match = re.search(r'Invoice\s*Number:?\s*(\d{6,8})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['City of Pembroke Pines'] = {'format': 'NNNNNNN', 'examples': ['2514869'], 'extract': _extract_city_of_pembroke_pines_invoice}

def _extract_a_1_little_john_invoice(text: str) -> Optional[str]:
    """A-1 Little John invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['A-1 Little John'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_a_1_little_john_invoice}

def _extract_pro_waste_services_invoice(text: str) -> Optional[str]:
    """Pro Waste Services invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Pro Waste Services'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_pro_waste_services_invoice}

def _extract_pascon_invoice(text: str) -> Optional[str]:
    """Pascon invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Pascon'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_pascon_invoice}

def _extract_tygarts_valley_sanitation_invoice(text: str) -> Optional[str]:
    """Tygarts Valley Sanitation invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Tygarts Valley Sanitation'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_tygarts_valley_sanitation_invoice}

def _extract_city_of_athens_ga_invoice(text: str) -> Optional[str]:
    """City of Athens GA invoice extractor"""
    match = re.search(r'INV[-\s]?(\d{4,6})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['City of Athens GA'] = {'format': 'INV-NNNNN', 'examples': ['21797'], 'extract': _extract_city_of_athens_ga_invoice}

def _extract_city_of_redwood_invoice(text: str) -> Optional[str]:
    """City of Redwood invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['City of Redwood'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_city_of_redwood_invoice}

def _extract_appalachian_waste_management_invoice(text: str) -> Optional[str]:
    """Appalachian Waste Management invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Appalachian Waste Management'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_appalachian_waste_management_invoice}

def _extract_transtrash_invoice(text: str) -> Optional[str]:
    """TransTrash invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['TransTrash'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_transtrash_invoice}

def _extract_empire_recycling_corporation_invoice(text: str) -> Optional[str]:
    """Empire Recycling Corporation invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Empire Recycling Corporation'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_empire_recycling_corporation_invoice}

def _extract_geodom_carting_invoice(text: str) -> Optional[str]:
    """Geodom Carting invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Geodom Carting'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_geodom_carting_invoice}

def _extract_sanitation_one_invoice(text: str) -> Optional[str]:
    """Sanitation One invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Sanitation One'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_sanitation_one_invoice}

def _extract_r_local_sanitation_invoice(text: str) -> Optional[str]:
    """R-Local Sanitation invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['R-Local Sanitation'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_r_local_sanitation_invoice}

def _extract_oak_disposal_services_invoice(text: str) -> Optional[str]:
    """Oak Disposal Services invoice extractor"""
    match = re.search(r'Invoice\s*#:?\s*(\d{4,6})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Oak Disposal Services'] = {'format': 'NNNNN', 'examples': ['79918'], 'extract': _extract_oak_disposal_services_invoice}

def _extract_total_reclaim_invoice(text: str) -> Optional[str]:
    """Total Reclaim invoice extractor"""
    match = re.search(r'INV[-\s]?(\d{5,7})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Total Reclaim'] = {'format': 'INV-NNNNNN', 'examples': ['023830'], 'extract': _extract_total_reclaim_invoice}

def _extract_bts_inc_invoice(text: str) -> Optional[str]:
    """BTS Inc invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['BTS Inc'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_bts_inc_invoice}

def _extract_express_disposal_invoice(text: str) -> Optional[str]:
    """Express Disposal invoice extractor"""
    match = re.search(r'INV[-\s]?(\d{5,7})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Express Disposal'] = {'format': 'INV-NNNNNN', 'examples': ['222373'], 'extract': _extract_express_disposal_invoice}

def _extract_cavossa_disposal_invoice(text: str) -> Optional[str]:
    """Cavossa Disposal invoice extractor"""
    match = re.search(r'Invoice\s*#:?\s*(\d{9,11})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Cavossa Disposal'] = {'format': 'NNNNNNNNNN', 'examples': ['0000318905'], 'extract': _extract_cavossa_disposal_invoice}

def _extract_city_of_bakersfield_invoice(text: str) -> Optional[str]:
    """City of Bakersfield invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['City of Bakersfield'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_city_of_bakersfield_invoice}

def _extract_pederson_sanitation_invoice(text: str) -> Optional[str]:
    """Pederson Sanitation invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Pederson Sanitation'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_pederson_sanitation_invoice}

def _extract_bud_s_clean_up_service_invoice(text: str) -> Optional[str]:
    """Bud's Clean Up Service invoice extractor"""
    match = re.search(r'Invoice\s*Number:?\s*(\d{9,11})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Bud\'s Clean Up Service'] = {'format': 'NNNNNNNNNN', 'examples': ['2509261348'], 'extract': _extract_bud_s_clean_up_service_invoice}

def _extract_edward_arnold_scrap_processors_invoice(text: str) -> Optional[str]:
    """Edward Arnold Scrap Processors invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Edward Arnold Scrap Processors'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_edward_arnold_scrap_processors_invoice}

def _extract_nitti_sanitation_invoice(text: str) -> Optional[str]:
    """Nitti Sanitation invoice extractor"""
    match = re.search(r'Invoice\s*No\.?:?\s*(\d{9,11})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Nitti Sanitation'] = {'format': 'NNNNNNNNNN', 'examples': ['0000779421'], 'extract': _extract_nitti_sanitation_invoice}

def _extract_city_of_dickson_invoice(text: str) -> Optional[str]:
    """City of Dickson invoice extractor"""
    match = re.search(r'Invoice\s*#:?\s*(\d{4,6})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['City of Dickson'] = {'format': 'NNNNN', 'examples': ['14691'], 'extract': _extract_city_of_dickson_invoice}

def _extract_haul_away_rubbish_invoice(text: str) -> Optional[str]:
    """Haul Away Rubbish invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Haul Away Rubbish'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_haul_away_rubbish_invoice}

def _extract_trashco_invoice(text: str) -> Optional[str]:
    """TRASHCO invoice extractor"""
    match = re.search(r'Invoice\s*#:?\s*(\d{4,6})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['TRASHCO'] = {'format': 'NNNNN', 'examples': ['76143'], 'extract': _extract_trashco_invoice}

def _extract_the_trash_man_invoice(text: str) -> Optional[str]:
    """The Trash Man invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['The Trash Man'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_the_trash_man_invoice}

def _extract_dependable_sanitation_invoice(text: str) -> Optional[str]:
    """Dependable Sanitation invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Dependable Sanitation'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_dependable_sanitation_invoice}

def _extract_las_vegas_recycling_invoice(text: str) -> Optional[str]:
    """Las Vegas Recycling invoice extractor"""
    match = re.search(r'Invoice\s*No\.?:?\s*(\d{4,6})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Las Vegas Recycling'] = {'format': 'NNNNN', 'examples': ['61054'], 'extract': _extract_las_vegas_recycling_invoice}

def _extract_rhino_waste_invoice(text: str) -> Optional[str]:
    """Rhino Waste invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Rhino Waste'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_rhino_waste_invoice}

def _extract_dan_s_r_us_sanitation_invoice(text: str) -> Optional[str]:
    """Dan's R Us Sanitation invoice extractor"""
    match = re.search(r'Invoice\s*Number:?\s*(\d{6,8})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Dan\'s R Us Sanitation'] = {'format': 'NNNNNNN', 'examples': ['9590908'], 'extract': _extract_dan_s_r_us_sanitation_invoice}

def _extract_city_of_sierra_vista_invoice(text: str) -> Optional[str]:
    """City of Sierra Vista invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['City of Sierra Vista'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_city_of_sierra_vista_invoice}

def _extract_kahut_waste_invoice(text: str) -> Optional[str]:
    """Kahut Waste invoice extractor"""
    match = re.search(r'Invoice\s*No\.?:?\s*(\d{7,9})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Kahut Waste'] = {'format': 'NNNNNNNN', 'examples': ['14862181'], 'extract': _extract_kahut_waste_invoice}

def _extract_b_l_disposal_invoice(text: str) -> Optional[str]:
    """B&L Disposal invoice extractor"""
    match = re.search(r'Invoice\s*#:?\s*(\d{6,8})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['B&L Disposal'] = {'format': 'NNNNNNN', 'examples': ['0009793'], 'extract': _extract_b_l_disposal_invoice}

def _extract_bulldog_disposal_invoice(text: str) -> Optional[str]:
    """Bulldog Disposal invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Bulldog Disposal'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_bulldog_disposal_invoice}

def _extract_major_waste_invoice(text: str) -> Optional[str]:
    """Major Waste invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Major Waste'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_major_waste_invoice}

def _extract_grace_hauling_invoice(text: str) -> Optional[str]:
    """Grace Hauling invoice extractor"""
    match = re.search(r'Invoice\s*#:?\s*(\d{6,8})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Grace Hauling'] = {'format': 'NNNNNNN', 'examples': ['1532897'], 'extract': _extract_grace_hauling_invoice}

def _extract_prestige_disposal_invoice(text: str) -> Optional[str]:
    """Prestige Disposal invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Prestige Disposal'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_prestige_disposal_invoice}

def _extract_vasco_road_landfill_invoice(text: str) -> Optional[str]:
    """Vasco Road Landfill invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Vasco Road Landfill'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_vasco_road_landfill_invoice}

def _extract_hem_service_company_invoice(text: str) -> Optional[str]:
    """HEM Service Company invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['HEM Service Company'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_hem_service_company_invoice}

def _extract_art_s_garbage_invoice(text: str) -> Optional[str]:
    """Art's Garbage invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Art\'s Garbage'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_art_s_garbage_invoice}

def _extract_miller_enterprises_invoice(text: str) -> Optional[str]:
    """Miller Enterprises invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Miller Enterprises'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_miller_enterprises_invoice}

def _extract_e_j_harrison_sons_invoice(text: str) -> Optional[str]:
    """E.J. Harrison & Sons invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['E.J. Harrison & Sons'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_e_j_harrison_sons_invoice}

def _extract_garden_state_waste_management_invoice(text: str) -> Optional[str]:
    """Garden State Waste Management invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Garden State Waste Management'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_garden_state_waste_management_invoice}

def _extract_norris_sanitation_invoice(text: str) -> Optional[str]:
    """Norris Sanitation invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Norris Sanitation'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_norris_sanitation_invoice}

def _extract_city_of_sevierville_invoice(text: str) -> Optional[str]:
    """City of Sevierville invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['City of Sevierville'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_city_of_sevierville_invoice}

def _extract_blue_ridge_waste_invoice(text: str) -> Optional[str]:
    """Blue Ridge Waste invoice extractor"""
    match = re.search(r'Invoice\s*#:?\s*(\d{4,6})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Blue Ridge Waste'] = {'format': 'NNNNN', 'examples': ['11427'], 'extract': _extract_blue_ridge_waste_invoice}

def _extract_city_of_hickory_invoice(text: str) -> Optional[str]:
    """City of Hickory invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['City of Hickory'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_city_of_hickory_invoice}

def _extract_midwest_sanitation_invoice(text: str) -> Optional[str]:
    """Midwest Sanitation invoice extractor"""
    match = re.search(r'Invoice\s*Number:?\s*(\d{5,7})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Midwest Sanitation'] = {'format': 'NNNNNN', 'examples': ['592748'], 'extract': _extract_midwest_sanitation_invoice}

def _extract_shred360_invoice(text: str) -> Optional[str]:
    """Shred360 invoice extractor"""
    match = re.search(r'Invoice\s*#:?\s*(\d{9,11})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Shred360'] = {'format': 'NNNNNNNNNN', 'examples': ['2779905012'], 'extract': _extract_shred360_invoice}

def _extract_westbury_paper_stock_invoice(text: str) -> Optional[str]:
    """Westbury Paper Stock invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Westbury Paper Stock'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_westbury_paper_stock_invoice}

def _extract_conigliaro_invoice(text: str) -> Optional[str]:
    """Conigliaro invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Conigliaro'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_conigliaro_invoice}

def _extract_gibson_truck_service_invoice(text: str) -> Optional[str]:
    """Gibson Truck Service invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Gibson Truck Service'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_gibson_truck_service_invoice}

def _extract_cleeton_sanitation_invoice(text: str) -> Optional[str]:
    """Cleeton Sanitation invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Cleeton Sanitation'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_cleeton_sanitation_invoice}

def _extract_kamps_pallets_invoice(text: str) -> Optional[str]:
    """Kamps Pallets invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Kamps Pallets'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_kamps_pallets_invoice}

def _extract_cedar_grove_invoice(text: str) -> Optional[str]:
    """Cedar Grove invoice extractor"""
    match = re.search(r'Invoice\s*#:?\s*(\d{9,11})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Cedar Grove'] = {'format': 'NNNNNNNNNN', 'examples': ['0000905952'], 'extract': _extract_cedar_grove_invoice}

def _extract_martin_environmental_invoice(text: str) -> Optional[str]:
    """Martin Environmental invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Martin Environmental'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_martin_environmental_invoice}

def _extract_city_of_red_wing_invoice(text: str) -> Optional[str]:
    """City of Red Wing invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['City of Red Wing'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_city_of_red_wing_invoice}

def _extract_southwest_sanitation_invoice(text: str) -> Optional[str]:
    """Southwest Sanitation invoice extractor"""
    match = re.search(r'Invoice\s*#:?\s*(\d{5,7})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Southwest Sanitation'] = {'format': 'NNNNNN', 'examples': ['128367'], 'extract': _extract_southwest_sanitation_invoice}

def _extract_garden_isle_disposal_invoice(text: str) -> Optional[str]:
    """Garden Isle Disposal invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Garden Isle Disposal'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_garden_isle_disposal_invoice}

def _extract_emery_county_sanitation_invoice(text: str) -> Optional[str]:
    """Emery County Sanitation invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Emery County Sanitation'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_emery_county_sanitation_invoice}

def _extract_bfi_waste_invoice(text: str) -> Optional[str]:
    """BFI Waste invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['BFI Waste'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_bfi_waste_invoice}

def _extract_william_sullivan_invoice(text: str) -> Optional[str]:
    """William Sullivan invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['William Sullivan'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_william_sullivan_invoice}

def _extract_crane_roll_off_invoice(text: str) -> Optional[str]:
    """Crane Roll-Off invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Crane Roll-Off'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_crane_roll_off_invoice}

def _extract_green_obky_invoice(text: str) -> Optional[str]:
    """Green OBKY invoice extractor"""
    match = re.search(r'Invoice\s*#:?\s*(\d{4,6})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Green OBKY'] = {'format': 'NNNNN', 'examples': ['22240'], 'extract': _extract_green_obky_invoice}

def _extract_heartland_waste_management_invoice(text: str) -> Optional[str]:
    """Heartland Waste Management invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Heartland Waste Management'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_heartland_waste_management_invoice}

def _extract_chrin_hauling_invoice(text: str) -> Optional[str]:
    """Chrin Hauling invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Chrin Hauling'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_chrin_hauling_invoice}

def _extract_aaa_disposal_service_invoice(text: str) -> Optional[str]:
    """AAA Disposal Service invoice extractor"""
    match = re.search(r'Inv\s*#:?\s*(\d{6,8})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['AAA Disposal Service'] = {'format': 'NNNNNNN', 'examples': ['1630152'], 'extract': _extract_aaa_disposal_service_invoice}

def _extract_willscot_invoice(text: str) -> Optional[str]:
    """WillScot invoice extractor"""
    match = re.search(r'Invoice\s*#:?\s*(\d{9,11})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['WillScot'] = {'format': 'NNNNNNNNNN', 'examples': ['9023698326'], 'extract': _extract_willscot_invoice}

def _extract_royal_document_destruction_invoice(text: str) -> Optional[str]:
    """Royal Document Destruction invoice extractor"""
    match = re.search(r'Invoice\s*#:?\s*(\d{6,8})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Royal Document Destruction'] = {'format': 'NNNNNNN', 'examples': ['1129898'], 'extract': _extract_royal_document_destruction_invoice}

def _extract_rick_taylor_invoice(text: str) -> Optional[str]:
    """Rick Taylor invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Rick Taylor'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_rick_taylor_invoice}

def _extract_klumm_brothers_invoice(text: str) -> Optional[str]:
    """Klumm Brothers invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Klumm Brothers'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_klumm_brothers_invoice}

def _extract_east_central_kansas_invoice(text: str) -> Optional[str]:
    """East Central Kansas invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['East Central Kansas'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_east_central_kansas_invoice}

def _extract_wisneski_westmoreland_invoice(text: str) -> Optional[str]:
    """Wisneski Westmoreland invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Wisneski Westmoreland'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_wisneski_westmoreland_invoice}

def _extract_a_i_pallets_invoice(text: str) -> Optional[str]:
    """A&I Pallets invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['A&I Pallets'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_a_i_pallets_invoice}

def _extract_csd_disposal_invoice(text: str) -> Optional[str]:
    """CSD Disposal invoice extractor"""
    match = re.search(r'Invoice\s*Number:?\s*(\d{8,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['CSD Disposal'] = {'format': 'NNNNNNNNN', 'examples': ['000714239'], 'extract': _extract_csd_disposal_invoice}

def _extract_hoss_disposal_invoice(text: str) -> Optional[str]:
    """Hoss Disposal invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Hoss Disposal'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_hoss_disposal_invoice}

def _extract_roberts_enterprises_invoice(text: str) -> Optional[str]:
    """Roberts Enterprises invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Roberts Enterprises'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_roberts_enterprises_invoice}

def _extract_city_of_mesa_invoice(text: str) -> Optional[str]:
    """City of Mesa invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['City of Mesa'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_city_of_mesa_invoice}

def _extract_direct_waste_services_invoice(text: str) -> Optional[str]:
    """Direct Waste Services invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Direct Waste Services'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_direct_waste_services_invoice}

def _extract_cowboy_sanitation_invoice(text: str) -> Optional[str]:
    """Cowboy Sanitation invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Cowboy Sanitation'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_cowboy_sanitation_invoice}

def _extract_apple_valley_waste_invoice(text: str) -> Optional[str]:
    """Apple Valley Waste invoice extractor"""
    match = re.search(r'Invoice\s*#:?\s*(\d{9,11})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Apple Valley Waste'] = {'format': 'NNNNNNNNNN', 'examples': ['0006806159'], 'extract': _extract_apple_valley_waste_invoice}

def _extract_richardson_waste_invoice(text: str) -> Optional[str]:
    """Richardson Waste invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Richardson Waste'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_richardson_waste_invoice}

def _extract_city_of_sherman_invoice(text: str) -> Optional[str]:
    """City of Sherman invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['City of Sherman'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_city_of_sherman_invoice}

def _extract_intermountain_disposal_invoice(text: str) -> Optional[str]:
    """Intermountain Disposal invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Intermountain Disposal'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_intermountain_disposal_invoice}

def _extract_chris_rizzo_trucking_invoice(text: str) -> Optional[str]:
    """Chris Rizzo Trucking invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Chris Rizzo Trucking'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_chris_rizzo_trucking_invoice}

def _extract_mr_e_invoice(text: str) -> Optional[str]:
    """MR & E invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['MR & E'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_mr_e_invoice}

def _extract_the_shred_truck_invoice(text: str) -> Optional[str]:
    """The Shred Truck invoice extractor"""
    match = re.search(r'Invoice\s*#:?\s*(\d{6,8})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['The Shred Truck'] = {'format': 'NNNNNNN', 'examples': ['0011039'], 'extract': _extract_the_shred_truck_invoice}

def _extract_ridgerunner_container_invoice(text: str) -> Optional[str]:
    """Ridgerunner Container invoice extractor"""
    match = re.search(r'Invoice\s*#:?\s*(\d{9,11})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Ridgerunner Container'] = {'format': 'NNNNNNNNNN', 'examples': ['0000196465'], 'extract': _extract_ridgerunner_container_invoice}

def _extract_ideal_trash_and_recycling_invoice(text: str) -> Optional[str]:
    """Ideal Trash and Recycling invoice extractor"""
    match = re.search(r'Invoice\s*Number:?\s*(\d{9,11})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Ideal Trash and Recycling'] = {'format': 'NNNNNNNNNN', 'examples': ['2510019341'], 'extract': _extract_ideal_trash_and_recycling_invoice}

def _extract_syracuse_haulers_invoice(text: str) -> Optional[str]:
    """Syracuse Haulers invoice extractor"""
    match = re.search(r'Invoice\s*#:?\s*(\d{5,7})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Syracuse Haulers'] = {'format': 'NNNNNN', 'examples': ['300025'], 'extract': _extract_syracuse_haulers_invoice}

def _extract_hometown_sanitation_invoice(text: str) -> Optional[str]:
    """Hometown Sanitation invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Hometown Sanitation'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_hometown_sanitation_invoice}

def _extract_cressman_sanitation_invoice(text: str) -> Optional[str]:
    """Cressman Sanitation invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Cressman Sanitation'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_cressman_sanitation_invoice}

def _extract_udp_tn_hauling_invoice(text: str) -> Optional[str]:
    """UDP TN Hauling invoice extractor"""
    match = re.search(r'INV[-\s]?(\d{4,6})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['UDP TN Hauling'] = {'format': 'INV-NNNNN', 'examples': ['24042'], 'extract': _extract_udp_tn_hauling_invoice}

def _extract_marborg_invoice(text: str) -> Optional[str]:
    """Marborg invoice extractor"""
    match = re.search(r'Invoice\s*Number:?\s*(\d{6,8})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Marborg'] = {'format': 'NNNNNNN', 'examples': ['6599409'], 'extract': _extract_marborg_invoice}

def _extract_united_rentals_invoice(text: str) -> Optional[str]:
    """United Rentals invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['United Rentals'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_united_rentals_invoice}

def _extract_bi_county_disposal_invoice(text: str) -> Optional[str]:
    """Bi-County Disposal invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Bi-County Disposal'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_bi_county_disposal_invoice}

def _extract_rapid_removal_invoice(text: str) -> Optional[str]:
    """Rapid Removal invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Rapid Removal'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_rapid_removal_invoice}

def _extract_lawrence_county_solid_waste_invoice(text: str) -> Optional[str]:
    """Lawrence County Solid Waste invoice extractor"""
    match = re.search(r'Invoice\s*No\.?:?\s*(\d{7,9})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Lawrence County Solid Waste'] = {'format': 'NNNNNNNN', 'examples': ['00162536'], 'extract': _extract_lawrence_county_solid_waste_invoice}

def _extract_elecke_invoice(text: str) -> Optional[str]:
    """Elecke invoice extractor"""
    match = re.search(r'Invoice\s*#:?\s*(\d{5,7})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Elecke'] = {'format': 'NNNNNN', 'examples': ['614610'], 'extract': _extract_elecke_invoice}

def _extract_ag_logistics_invoice(text: str) -> Optional[str]:
    """AG Logistics invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['AG Logistics'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_ag_logistics_invoice}

def _extract_tri_city_disposal_invoice(text: str) -> Optional[str]:
    """Tri-City Disposal invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Tri-City Disposal'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_tri_city_disposal_invoice}

def _extract_local_waste_solution_invoice(text: str) -> Optional[str]:
    """Local Waste Solution invoice extractor"""
    match = re.search(r'Invoice\s*No\.?:?\s*(\d{4,6})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Local Waste Solution'] = {'format': 'NNNNN', 'examples': ['56842'], 'extract': _extract_local_waste_solution_invoice}

def _extract_waste_express_invoice(text: str) -> Optional[str]:
    """Waste Express invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Waste Express'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_waste_express_invoice}

def _extract_coastal_environmental_service_invoice(text: str) -> Optional[str]:
    """Coastal Environmental Service invoice extractor"""
    match = re.search(r'INV[-\s]?(\d{5,7})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Coastal Environmental Service'] = {'format': 'INV-NNNNNN', 'examples': ['421692'], 'extract': _extract_coastal_environmental_service_invoice}

def _extract_paso_robles_waste_invoice(text: str) -> Optional[str]:
    """Paso Robles Waste invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Paso Robles Waste'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_paso_robles_waste_invoice}

def _extract_green_guy_recycling_invoice(text: str) -> Optional[str]:
    """Green Guy Recycling invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Green Guy Recycling'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_green_guy_recycling_invoice}

def _extract_washler_garbage_invoice(text: str) -> Optional[str]:
    """Washler Garbage invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Washler Garbage'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_washler_garbage_invoice}

def _extract_ontario_municipal_invoice(text: str) -> Optional[str]:
    """Ontario Municipal invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Ontario Municipal'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_ontario_municipal_invoice}

def _extract_parish_disposal_invoice(text: str) -> Optional[str]:
    """Parish Disposal invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Parish Disposal'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_parish_disposal_invoice}

def _extract_city_of_casper_invoice(text: str) -> Optional[str]:
    """City of Casper invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['City of Casper'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_city_of_casper_invoice}

def _extract_snake_river_rubbish_invoice(text: str) -> Optional[str]:
    """Snake River Rubbish invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Snake River Rubbish'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_snake_river_rubbish_invoice}

def _extract_cwrr_invoice(text: str) -> Optional[str]:
    """CWRR invoice extractor"""
    match = re.search(r'Invoice\s*No\.?:?\s*(\d{4,6})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['CWRR'] = {'format': 'NNNNN', 'examples': ['52713'], 'extract': _extract_cwrr_invoice}

def _extract_andy_gump_invoice(text: str) -> Optional[str]:
    """Andy Gump invoice extractor"""
    match = re.search(r'INV[-\s]?(\d{6,8})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Andy Gump'] = {'format': 'INV-NNNNNNN', 'examples': ['1261712'], 'extract': _extract_andy_gump_invoice}

def _extract_allstate_equipment_services_invoice(text: str) -> Optional[str]:
    """Allstate Equipment Services invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Allstate Equipment Services'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_allstate_equipment_services_invoice}

def _extract_howie_s_trash_service_invoice(text: str) -> Optional[str]:
    """Howie's Trash Service invoice extractor"""
    match = re.search(r'Invoice\s*Number:?\s*(\d{7,9})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Howie\'s Trash Service'] = {'format': 'NNNNNNNN', 'examples': ['12160500'], 'extract': _extract_howie_s_trash_service_invoice}

def _extract_am_disposal_invoice(text: str) -> Optional[str]:
    """AM Disposal invoice extractor"""
    match = re.search(r'Invoice\s*#:?\s*(\d{5,7})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['AM Disposal'] = {'format': 'NNNNNN', 'examples': ['002837'], 'extract': _extract_am_disposal_invoice}

def _extract_eco_sanitation_invoice(text: str) -> Optional[str]:
    """Eco Sanitation invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Eco Sanitation'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_eco_sanitation_invoice}

def _extract_coos_bay_sanitary_invoice(text: str) -> Optional[str]:
    """Coos Bay Sanitary invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Coos Bay Sanitary'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_coos_bay_sanitary_invoice}

def _extract_city_of_visalia_invoice(text: str) -> Optional[str]:
    """City of Visalia invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['City of Visalia'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_city_of_visalia_invoice}

def _extract_ads_solid_waste_invoice(text: str) -> Optional[str]:
    """ADS Solid Waste invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['ADS Solid Waste'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_ads_solid_waste_invoice}

def _extract_city_of_boynton_beach_invoice(text: str) -> Optional[str]:
    """City of Boynton Beach invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['City of Boynton Beach'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_city_of_boynton_beach_invoice}

def _extract_ctl_washington_invoice(text: str) -> Optional[str]:
    """CTL Washington invoice extractor"""
    match = re.search(r'INV[-\s]?(\d{4,6})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['CTL Washington'] = {'format': 'INV-NNNNN', 'examples': ['18729'], 'extract': _extract_ctl_washington_invoice}

def _extract_waste_path_invoice(text: str) -> Optional[str]:
    """Waste Path invoice extractor"""
    match = re.search(r'Invoice\s*#:?\s*(\d{6,8})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Waste Path'] = {'format': 'NNNNNNN', 'examples': ['1004438'], 'extract': _extract_waste_path_invoice}

def _extract_southern_sanitation_invoice(text: str) -> Optional[str]:
    """Southern Sanitation invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Southern Sanitation'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_southern_sanitation_invoice}

def _extract_city_of_fayette_invoice(text: str) -> Optional[str]:
    """City of Fayette invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['City of Fayette'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_city_of_fayette_invoice}

def _extract_satellite_shelters_invoice(text: str) -> Optional[str]:
    """Satellite Shelters invoice extractor"""
    match = re.search(r'INV[-\s]?(\d{5,7})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Satellite Shelters'] = {'format': 'INV-NNNNNN', 'examples': ['916844'], 'extract': _extract_satellite_shelters_invoice}

def _extract_cram_a_lot_invoice(text: str) -> Optional[str]:
    """Cram-A-Lot invoice extractor"""
    match = re.search(r'Invoice\s*Number:?\s*(\d{6,8})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Cram-A-Lot'] = {'format': 'NNNNNNN', 'examples': ['3025722'], 'extract': _extract_cram_a_lot_invoice}

def _extract_city_of_buford_invoice(text: str) -> Optional[str]:
    """City of Buford invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['City of Buford'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_city_of_buford_invoice}

def _extract_premier_disposal_invoice(text: str) -> Optional[str]:
    """Premier Disposal invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Premier Disposal'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_premier_disposal_invoice}

def _extract_sage_disposal_invoice(text: str) -> Optional[str]:
    """Sage Disposal invoice extractor"""
    match = re.search(r'Invoice\s*#:?\s*(\d{4,6})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Sage Disposal'] = {'format': 'NNNNN', 'examples': ['18586'], 'extract': _extract_sage_disposal_invoice}

def _extract_porter_trash_invoice(text: str) -> Optional[str]:
    """Porter Trash invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Porter Trash'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_porter_trash_invoice}

def _extract_grand_rapids_iron_invoice(text: str) -> Optional[str]:
    """Grand Rapids Iron invoice extractor"""
    match = re.search(r'Invoice\s*#:?\s*(\d{5,7})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Grand Rapids Iron'] = {'format': 'NNNNNN', 'examples': ['042677'], 'extract': _extract_grand_rapids_iron_invoice}

def _extract_f_l_construction_invoice(text: str) -> Optional[str]:
    """F & L Construction invoice extractor"""
    match = re.search(r'Invoice\s*No\.?:?\s*(\d{9,11})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['F & L Construction'] = {'format': 'NNNNNNNNNN', 'examples': ['0000045351'], 'extract': _extract_f_l_construction_invoice}

def _extract_abs_sanitation_invoice(text: str) -> Optional[str]:
    """ABS Sanitation invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['ABS Sanitation'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_abs_sanitation_invoice}

def _extract_town_of_limon_invoice(text: str) -> Optional[str]:
    """Town of Limon invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Town of Limon'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_town_of_limon_invoice}

def _extract_mosdell_sanitation_invoice(text: str) -> Optional[str]:
    """Mosdell Sanitation invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Mosdell Sanitation'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_mosdell_sanitation_invoice}

def _extract_city_of_sulphur_springs_invoice(text: str) -> Optional[str]:
    """City of Sulphur Springs invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['City of Sulphur Springs'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_city_of_sulphur_springs_invoice}

def _extract_orlando_recycling_invoice(text: str) -> Optional[str]:
    """Orlando Recycling invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Orlando Recycling'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_orlando_recycling_invoice}

def _extract_sonoran_ranch_invoice(text: str) -> Optional[str]:
    """Sonoran Ranch invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Sonoran Ranch'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_sonoran_ranch_invoice}

def _extract_wft_waste_invoice(text: str) -> Optional[str]:
    """WFT Waste invoice extractor"""
    match = re.search(r'Inv\s*#:?\s*(\d{5,7})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['WFT Waste'] = {'format': 'NNNNNN', 'examples': ['154553'], 'extract': _extract_wft_waste_invoice}

def _extract_food_to_power_invoice(text: str) -> Optional[str]:
    """Food To Power invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Food To Power'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_food_to_power_invoice}

def _extract_ed_s_disposal_invoice(text: str) -> Optional[str]:
    """Ed's Disposal invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Ed\'s Disposal'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_ed_s_disposal_invoice}

def _extract_kuerth_s_disposal_invoice(text: str) -> Optional[str]:
    """Kuerth's Disposal invoice extractor"""
    match = re.search(r'Invoice\s*#:?\s*(\d{4,6})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Kuerth\'s Disposal'] = {'format': 'NNNNN', 'examples': ['60693'], 'extract': _extract_kuerth_s_disposal_invoice}

def _extract_town_of_lake_park_invoice(text: str) -> Optional[str]:
    """Town of Lake Park invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Town of Lake Park'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_town_of_lake_park_invoice}

def _extract_bp_trucking_invoice(text: str) -> Optional[str]:
    """BP Trucking invoice extractor"""
    match = re.search(r'Invoice\s*Number:?\s*(\d{9,11})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['BP Trucking'] = {'format': 'NNNNNNNNNN', 'examples': ['0000472207'], 'extract': _extract_bp_trucking_invoice}

def _extract_pete_and_pete_invoice(text: str) -> Optional[str]:
    """Pete and Pete invoice extractor"""
    match = re.search(r'INV[-\s]?(\d{5,7})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Pete and Pete'] = {'format': 'INV-NNNNNN', 'examples': ['111658'], 'extract': _extract_pete_and_pete_invoice}

def _extract_mid_south_waste_invoice(text: str) -> Optional[str]:
    """Mid South Waste invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Mid South Waste'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_mid_south_waste_invoice}

def _extract_penn_waste_invoice(text: str) -> Optional[str]:
    """Penn Waste invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Penn Waste'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_penn_waste_invoice}

def _extract_wastevision_invoice(text: str) -> Optional[str]:
    """WasteVision invoice extractor"""
    match = re.search(r'INV[-\s]?(\d{9,11})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['WasteVision'] = {'format': 'INV-NNNNNNNNNN', 'examples': ['0000000582'], 'extract': _extract_wastevision_invoice}

def _extract_veolia_invoice(text: str) -> Optional[str]:
    """Veolia invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Veolia'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_veolia_invoice}

def _extract_tennis_sanitation_invoice(text: str) -> Optional[str]:
    """Tennis Sanitation invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Tennis Sanitation'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_tennis_sanitation_invoice}

def _extract_bruin_waste_management_invoice(text: str) -> Optional[str]:
    """Bruin Waste Management invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Bruin Waste Management'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_bruin_waste_management_invoice}

def _extract_hilltopper_refuse_invoice(text: str) -> Optional[str]:
    """Hilltopper Refuse invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Hilltopper Refuse'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_hilltopper_refuse_invoice}

def _extract_hotchkiss_disposal_invoice(text: str) -> Optional[str]:
    """Hotchkiss Disposal invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Hotchkiss Disposal'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_hotchkiss_disposal_invoice}

def _extract_hart_sanitation_invoice(text: str) -> Optional[str]:
    """Hart Sanitation invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Hart Sanitation'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_hart_sanitation_invoice}

def _extract_roller_industrial_invoice(text: str) -> Optional[str]:
    """Roller Industrial invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Roller Industrial'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_roller_industrial_invoice}

def _extract_city_of_tulare_invoice(text: str) -> Optional[str]:
    """City of Tulare invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['City of Tulare'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_city_of_tulare_invoice}

def _extract_jettison_environmental_invoice(text: str) -> Optional[str]:
    """Jettison Environmental invoice extractor"""
    match = re.search(r'Invoice\s*#:?\s*(\d{7,9})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Jettison Environmental'] = {'format': 'NNNNNNNN', 'examples': ['52100522'], 'extract': _extract_jettison_environmental_invoice}

def _extract_mars_city_of_beatrice_invoice(text: str) -> Optional[str]:
    """MARS City of Beatrice invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['MARS City of Beatrice'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_mars_city_of_beatrice_invoice}

def _extract_amg_resources_invoice(text: str) -> Optional[str]:
    """AMG Resources invoice extractor"""
    match = re.search(r'Invoice\s*No\.?:?\s*(\d{5,7})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['AMG Resources'] = {'format': 'NNNNNN', 'examples': ['599767'], 'extract': _extract_amg_resources_invoice}

def _extract_golden_environmental_invoice(text: str) -> Optional[str]:
    """Golden Environmental invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Golden Environmental'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_golden_environmental_invoice}

def _extract_city_of_mesquite_invoice(text: str) -> Optional[str]:
    """City of Mesquite invoice extractor"""
    match = re.search(r'Invoice\s*Number:?\s*(\d{4,6})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['City of Mesquite'] = {'format': 'NNNNN', 'examples': ['33338'], 'extract': _extract_city_of_mesquite_invoice}

def _extract_madras_sanitary_service_invoice(text: str) -> Optional[str]:
    """Madras Sanitary Service invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Madras Sanitary Service'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_madras_sanitary_service_invoice}

def _extract_rubatino_refuse_invoice(text: str) -> Optional[str]:
    """Rubatino Refuse invoice extractor"""
    match = re.search(r'Invoice\s*Number:?\s*(\d{6,8})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Rubatino Refuse'] = {'format': 'NNNNNNN', 'examples': ['4065920'], 'extract': _extract_rubatino_refuse_invoice}

def _extract_allen_disposal_invoice(text: str) -> Optional[str]:
    """Allen Disposal invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Allen Disposal'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_allen_disposal_invoice}

def _extract_lk_specialties_invoice(text: str) -> Optional[str]:
    """LK Specialties invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['LK Specialties'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_lk_specialties_invoice}

def _extract_town_country_disposal_invoice(text: str) -> Optional[str]:
    """Town & Country Disposal invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Town & Country Disposal'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_town_country_disposal_invoice}

def _extract_thompson_sanitation_invoice(text: str) -> Optional[str]:
    """Thompson Sanitation invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Thompson Sanitation'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_thompson_sanitation_invoice}

def _extract_miles_city_sanitation_invoice(text: str) -> Optional[str]:
    """Miles City Sanitation invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Miles City Sanitation'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_miles_city_sanitation_invoice}

def _extract_waterman_recy_disposal_invoice(text: str) -> Optional[str]:
    """Waterman Recy & Disposal invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Waterman Recy & Disposal'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_waterman_recy_disposal_invoice}

def _extract_nauset_disposal_invoice(text: str) -> Optional[str]:
    """Nauset Disposal invoice extractor"""
    match = re.search(r'Invoice\s*No\.?:?\s*(\d{6,8})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Nauset Disposal'] = {'format': 'NNNNNNN', 'examples': ['1820226'], 'extract': _extract_nauset_disposal_invoice}

def _extract_mazza_recycling_invoice(text: str) -> Optional[str]:
    """Mazza Recycling invoice extractor"""
    match = re.search(r'Invoice\s*No\.?:?\s*(\d{9,11})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Mazza Recycling'] = {'format': 'NNNNNNNNNN', 'examples': ['0001879530'], 'extract': _extract_mazza_recycling_invoice}

def _extract_chambersburg_waste_paper_invoice(text: str) -> Optional[str]:
    """Chambersburg Waste Paper invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Chambersburg Waste Paper'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_chambersburg_waste_paper_invoice}

def _extract_kern_county_public_works_invoice(text: str) -> Optional[str]:
    """Kern County Public Works invoice extractor"""
    match = re.search(r'Invoice\s*Number:?\s*(\d{4,6})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Kern County Public Works'] = {'format': 'NNNNN', 'examples': ['49299'], 'extract': _extract_kern_county_public_works_invoice}

def _extract_timberline_llc_invoice(text: str) -> Optional[str]:
    """Timberline LLC invoice extractor"""
    match = re.search(r'Inv\s*#:?\s*(\d{5,7})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Timberline LLC'] = {'format': 'NNNNNN', 'examples': ['725841'], 'extract': _extract_timberline_llc_invoice}

def _extract_junk_removed_now_invoice(text: str) -> Optional[str]:
    """Junk Removed Now invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Junk Removed Now'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_junk_removed_now_invoice}

def _extract_new_prague_sanitary_invoice(text: str) -> Optional[str]:
    """New Prague Sanitary invoice extractor"""
    match = re.search(r'Invoice\s*#:?\s*(\d{5,7})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['New Prague Sanitary'] = {'format': 'NNNNNN', 'examples': ['171155'], 'extract': _extract_new_prague_sanitary_invoice}

def _extract_city_of_oakland_park_invoice(text: str) -> Optional[str]:
    """City of Oakland Park invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['City of Oakland Park'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_city_of_oakland_park_invoice}

def _extract_miamitown_auto_parts_invoice(text: str) -> Optional[str]:
    """Miamitown Auto Parts invoice extractor"""
    match = re.search(r'Invoice\s*#:?\s*(\d{5,7})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Miamitown Auto Parts'] = {'format': 'NNNNNN', 'examples': ['489207'], 'extract': _extract_miamitown_auto_parts_invoice}

def _extract_olcese_waste_services_invoice(text: str) -> Optional[str]:
    """Olcese Waste Services invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Olcese Waste Services'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_olcese_waste_services_invoice}

def _extract_going_green_recycle_invoice(text: str) -> Optional[str]:
    """Going Green Recycle invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Going Green Recycle'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_going_green_recycle_invoice}

def _extract_h_town_hauling_invoice(text: str) -> Optional[str]:
    """H-Town Hauling invoice extractor"""
    match = re.search(r'Invoice\s*#:?\s*(\d{6,8})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['H-Town Hauling'] = {'format': 'NNNNNNN', 'examples': ['1925085'], 'extract': _extract_h_town_hauling_invoice}

def _extract_deep_south_sanitation_invoice(text: str) -> Optional[str]:
    """Deep South Sanitation invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Deep South Sanitation'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_deep_south_sanitation_invoice}

def _extract_diamond_disposal_invoice(text: str) -> Optional[str]:
    """Diamond Disposal invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Diamond Disposal'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_diamond_disposal_invoice}

def _extract_hugill_sanitation_invoice(text: str) -> Optional[str]:
    """Hugill Sanitation invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Hugill Sanitation'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_hugill_sanitation_invoice}

def _extract_dillon_disposal_invoice(text: str) -> Optional[str]:
    """Dillon Disposal invoice extractor"""
    match = re.search(r'Invoice\s*Number:?\s*(\d{5,7})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Dillon Disposal'] = {'format': 'NNNNNN', 'examples': ['265818'], 'extract': _extract_dillon_disposal_invoice}

def _extract_city_of_mcdonough_invoice(text: str) -> Optional[str]:
    """City of McDonough invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['City of McDonough'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_city_of_mcdonough_invoice}

def _extract_suburban_disposal_invoice(text: str) -> Optional[str]:
    """Suburban Disposal invoice extractor"""
    match = re.search(r'Invoice\s*#:?\s*(\d{6,8})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Suburban Disposal'] = {'format': 'NNNNNNN', 'examples': ['2900226'], 'extract': _extract_suburban_disposal_invoice}

def _extract_b_n_c_trash_service_invoice(text: str) -> Optional[str]:
    """B-N-C Trash Service invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['B-N-C Trash Service'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_b_n_c_trash_service_invoice}

def _extract_shank_waste_invoice(text: str) -> Optional[str]:
    """Shank Waste invoice extractor"""
    match = re.search(r'Invoice\s*Number:?\s*(\d{5,7})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Shank Waste'] = {'format': 'NNNNNN', 'examples': ['218668'], 'extract': _extract_shank_waste_invoice}

def _extract_quality_waste_invoice(text: str) -> Optional[str]:
    """Quality Waste invoice extractor"""
    match = re.search(r'Invoice\s*No\.?:?\s*(\d{9,11})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Quality Waste'] = {'format': 'NNNNNNNNNN', 'examples': ['0000067949'], 'extract': _extract_quality_waste_invoice}

def _extract_trash_control_invoice(text: str) -> Optional[str]:
    """Trash Control invoice extractor"""
    match = re.search(r'Invoice\s*#:?\s*(\d{5,7})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Trash Control'] = {'format': 'NNNNNN', 'examples': ['239027'], 'extract': _extract_trash_control_invoice}

def _extract_steve_s_sanitation_invoice(text: str) -> Optional[str]:
    """Steve's Sanitation invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Steve\'s Sanitation'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_steve_s_sanitation_invoice}

def _extract_young_refuse_invoice(text: str) -> Optional[str]:
    """Young Refuse invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Young Refuse'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_young_refuse_invoice}

def _extract_sunshine_disposal_recycling_invoice(text: str) -> Optional[str]:
    """Sunshine Disposal & Recycling invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Sunshine Disposal & Recycling'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_sunshine_disposal_recycling_invoice}

def _extract_midwest_disposal_il_invoice(text: str) -> Optional[str]:
    """Midwest Disposal IL invoice extractor"""
    match = re.search(r'Invoice\s*Number:?\s*(\d{9,11})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Midwest Disposal IL'] = {'format': 'NNNNNNNNNN', 'examples': ['2505200184'], 'extract': _extract_midwest_disposal_il_invoice}

def _extract_miedema_sanitation_invoice(text: str) -> Optional[str]:
    """Miedema Sanitation invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Miedema Sanitation'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_miedema_sanitation_invoice}

def _extract_reliable_sanitation_invoice(text: str) -> Optional[str]:
    """Reliable Sanitation invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Reliable Sanitation'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_reliable_sanitation_invoice}

def _extract_greenwaste_invoice(text: str) -> Optional[str]:
    """GreenWaste invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['GreenWaste'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_greenwaste_invoice}

def _extract_nowrush_recycling_invoice(text: str) -> Optional[str]:
    """Nowrush Recycling invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Nowrush Recycling'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_nowrush_recycling_invoice}

def _extract_pro_disposal_invoice(text: str) -> Optional[str]:
    """Pro Disposal invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Pro Disposal'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_pro_disposal_invoice}

def _extract_city_of_cookeville_invoice(text: str) -> Optional[str]:
    """City of Cookeville invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['City of Cookeville'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_city_of_cookeville_invoice}

def _extract_talon_sanitation_invoice(text: str) -> Optional[str]:
    """Talon Sanitation invoice extractor"""
    match = re.search(r'Invoice\s*Number:?\s*(\d{9,11})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Talon Sanitation'] = {'format': 'NNNNNNNNNN', 'examples': ['2509160130'], 'extract': _extract_talon_sanitation_invoice}

def _extract_dugger_trash_service_invoice(text: str) -> Optional[str]:
    """Dugger Trash Service invoice extractor"""
    match = re.search(r'Invoice\s*Number:?\s*(\d{9,11})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Dugger Trash Service'] = {'format': 'NNNNNNNNNN', 'examples': ['2502261818'], 'extract': _extract_dugger_trash_service_invoice}

def _extract_royal_oak_recycling_invoice(text: str) -> Optional[str]:
    """Royal Oak Recycling invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Royal Oak Recycling'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_royal_oak_recycling_invoice}

def _extract_equipment_depot_northeast_invoice(text: str) -> Optional[str]:
    """Equipment Depot Northeast invoice extractor"""
    match = re.search(r'Invoice\s*#:?\s*(\d{5,7})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Equipment Depot Northeast'] = {'format': 'NNNNNN', 'examples': ['961598'], 'extract': _extract_equipment_depot_northeast_invoice}

def _extract_3r_technology_invoice(text: str) -> Optional[str]:
    """3R Technology invoice extractor"""
    match = re.search(r'INV[-\s]?(\d{4,6})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['3R Technology'] = {'format': 'INV-NNNNN', 'examples': ['17544'], 'extract': _extract_3r_technology_invoice}

def _extract_recycling_services_of_florida_invoice(text: str) -> Optional[str]:
    """Recycling Services of Florida invoice extractor"""
    match = re.search(r'Invoice\s*No\.?:?\s*(\d{9,11})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Recycling Services of Florida'] = {'format': 'NNNNNNNNNN', 'examples': ['0000129533'], 'extract': _extract_recycling_services_of_florida_invoice}

def _extract_haul_away_waste_invoice(text: str) -> Optional[str]:
    """Haul Away Waste invoice extractor"""
    match = re.search(r'INV[-\s]?(\d{4,6})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Haul Away Waste'] = {'format': 'INV-NNNNN', 'examples': ['15250'], 'extract': _extract_haul_away_waste_invoice}

def _extract_burgmeier_s_hauling_invoice(text: str) -> Optional[str]:
    """Burgmeier's Hauling invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Burgmeier\'s Hauling'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_burgmeier_s_hauling_invoice}

def _extract_brask_enterprises_invoice(text: str) -> Optional[str]:
    """Brask Enterprises invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Brask Enterprises'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_brask_enterprises_invoice}

def _extract_city_of_columbia_mo_invoice(text: str) -> Optional[str]:
    """City of Columbia MO invoice extractor"""
    match = re.search(r'Invoice\s*#:?\s*(\d{5,7})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['City of Columbia MO'] = {'format': 'NNNNNN', 'examples': ['815132'], 'extract': _extract_city_of_columbia_mo_invoice}

def _extract_circle_sanitation_invoice(text: str) -> Optional[str]:
    """Circle Sanitation invoice extractor"""
    match = re.search(r'Invoice\s*#:?\s*(\d{4,6})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Circle Sanitation'] = {'format': 'NNNNN', 'examples': ['87865'], 'extract': _extract_circle_sanitation_invoice}

def _extract_l_l_site_services_invoice(text: str) -> Optional[str]:
    """L&L Site Services invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['L&L Site Services'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_l_l_site_services_invoice}

def _extract_lemhi_sanitation_invoice(text: str) -> Optional[str]:
    """Lemhi Sanitation invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Lemhi Sanitation'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_lemhi_sanitation_invoice}

def _extract_waste_services_manchester_invoice(text: str) -> Optional[str]:
    """Waste Services Manchester invoice extractor"""
    match = re.search(r'Invoice\s*#:?\s*(\d{9,11})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Waste Services Manchester'] = {'format': 'NNNNNNNNNN', 'examples': ['2506301020'], 'extract': _extract_waste_services_manchester_invoice}

def _extract_sunny_trash_hauling_invoice(text: str) -> Optional[str]:
    """Sunny Trash Hauling invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Sunny Trash Hauling'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_sunny_trash_hauling_invoice}

def _extract_blue_moon_invoice(text: str) -> Optional[str]:
    """Blue Moon invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Blue Moon'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_blue_moon_invoice}

def _extract_town_country_sanitation_invoice(text: str) -> Optional[str]:
    """Town & Country Sanitation invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Town & Country Sanitation'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_town_country_sanitation_invoice}

def _extract_d_s_portable_toilets_invoice(text: str) -> Optional[str]:
    """D&S Portable Toilets invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['D&S Portable Toilets'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_d_s_portable_toilets_invoice}

def _extract_trinity_disposal_invoice(text: str) -> Optional[str]:
    """Trinity Disposal invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Trinity Disposal'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_trinity_disposal_invoice}

def _extract_wyoming_waste_services_invoice(text: str) -> Optional[str]:
    """Wyoming Waste Services invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Wyoming Waste Services'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_wyoming_waste_services_invoice}

def _extract_weidle_sanitation_invoice(text: str) -> Optional[str]:
    """Weidle Sanitation invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Weidle Sanitation'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_weidle_sanitation_invoice}

def _extract_hepaco_invoice(text: str) -> Optional[str]:
    """Hepaco invoice extractor"""
    match = re.search(r'Invoice\s*No\.?:?\s*(\d{9,11})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Hepaco'] = {'format': 'NNNNNNNNNN', 'examples': ['1005338322'], 'extract': _extract_hepaco_invoice}

def _extract_greif_invoice(text: str) -> Optional[str]:
    """Greif invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Greif'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_greif_invoice}

def _extract_waste_reduction_sys_invoice(text: str) -> Optional[str]:
    """Waste Reduction Sys invoice extractor"""
    match = re.search(r'Invoice\s*#:?\s*(\d{4,6})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Waste Reduction Sys'] = {'format': 'NNNNN', 'examples': ['50267'], 'extract': _extract_waste_reduction_sys_invoice}

def _extract_wright_s_environmental_invoice(text: str) -> Optional[str]:
    """Wright's Environmental invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Wright\'s Environmental'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_wright_s_environmental_invoice}

def _extract_bcc_waste_solutions_invoice(text: str) -> Optional[str]:
    """BCC Waste Solutions invoice extractor"""
    match = re.search(r'Invoice\s*No\.?:?\s*(\d{9,11})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['BCC Waste Solutions'] = {'format': 'NNNNNNNNNN', 'examples': ['0000609973'], 'extract': _extract_bcc_waste_solutions_invoice}

def _extract_madison_materials_invoice(text: str) -> Optional[str]:
    """Madison Materials invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Madison Materials'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_madison_materials_invoice}

def _extract_countryside_disposal_invoice(text: str) -> Optional[str]:
    """Countryside Disposal invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Countryside Disposal'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_countryside_disposal_invoice}

def _extract_seaside_waste_invoice(text: str) -> Optional[str]:
    """Seaside Waste invoice extractor"""
    match = re.search(r'Invoice\s*#:?\s*(\d{5,7})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Seaside Waste'] = {'format': 'NNNNNN', 'examples': ['267428'], 'extract': _extract_seaside_waste_invoice}

def _extract_fayette_waste_invoice(text: str) -> Optional[str]:
    """Fayette Waste invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Fayette Waste'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_fayette_waste_invoice}

def _extract_document_destruction_of_virginia_invoice(text: str) -> Optional[str]:
    """Document Destruction of Virginia invoice extractor"""
    match = re.search(r'Invoice\s*#:?\s*(\d{5,7})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Document Destruction of Virginia'] = {'format': 'NNNNNN', 'examples': ['429637'], 'extract': _extract_document_destruction_of_virginia_invoice}

def _extract_uribe_refuse_invoice(text: str) -> Optional[str]:
    """Uribe Refuse invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Uribe Refuse'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_uribe_refuse_invoice}

def _extract_waste_harmonics_invoice(text: str) -> Optional[str]:
    """Waste Harmonics invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Waste Harmonics'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_waste_harmonics_invoice}

def _extract_iron_city_express_invoice(text: str) -> Optional[str]:
    """Iron City Express invoice extractor"""
    match = re.search(r'Invoice\s*Number:?\s*(\d{5,7})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Iron City Express'] = {'format': 'NNNNNN', 'examples': ['360063'], 'extract': _extract_iron_city_express_invoice}

def _extract_sutton_disposal_invoice(text: str) -> Optional[str]:
    """Sutton Disposal invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Sutton Disposal'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_sutton_disposal_invoice}

def _extract_eastern_waste_invoice(text: str) -> Optional[str]:
    """Eastern Waste invoice extractor"""
    match = re.search(r'Invoice\s*#:?\s*(\d{4,6})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Eastern Waste'] = {'format': 'NNNNN', 'examples': ['47522'], 'extract': _extract_eastern_waste_invoice}

def _extract_pacific_disposal_invoice(text: str) -> Optional[str]:
    """Pacific Disposal invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Pacific Disposal'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_pacific_disposal_invoice}

def _extract_engebretson_sons_invoice(text: str) -> Optional[str]:
    """Engebretson & Sons invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Engebretson & Sons'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_engebretson_sons_invoice}

def _extract_city_of_great_falls_invoice(text: str) -> Optional[str]:
    """City of Great Falls invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['City of Great Falls'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_city_of_great_falls_invoice}

def _extract_waste_advantage_invoice(text: str) -> Optional[str]:
    """Waste Advantage invoice extractor"""
    match = re.search(r'Invoice\s*#:?\s*(\d{5,7})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Waste Advantage'] = {'format': 'NNNNNN', 'examples': ['517872'], 'extract': _extract_waste_advantage_invoice}

def _extract_hill_country_waste_invoice(text: str) -> Optional[str]:
    """Hill Country Waste invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Hill Country Waste'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_hill_country_waste_invoice}

def _extract_waste_control_invoice(text: str) -> Optional[str]:
    """Waste Control invoice extractor"""
    match = re.search(r'Invoice\s*#:?\s*(\d{9,11})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Waste Control'] = {'format': 'NNNNNNNNNN', 'examples': ['0003912198'], 'extract': _extract_waste_control_invoice}

def _extract_junk_solutions_invoice(text: str) -> Optional[str]:
    """Junk Solutions invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Junk Solutions'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_junk_solutions_invoice}

def _extract_ace_equipment_company_invoice(text: str) -> Optional[str]:
    """Ace Equipment Company invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Ace Equipment Company'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_ace_equipment_company_invoice}

def _extract_city_of_st_anthony_invoice(text: str) -> Optional[str]:
    """City of St Anthony invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['City of St Anthony'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_city_of_st_anthony_invoice}

def _extract_national_waste_disposal_invoice(text: str) -> Optional[str]:
    """National Waste & Disposal invoice extractor"""
    match = re.search(r'Invoice\s*No\.?:?\s*(\d{9,11})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['National Waste & Disposal'] = {'format': 'NNNNNNNNNN', 'examples': ['0000251516'], 'extract': _extract_national_waste_disposal_invoice}

def _extract_earthwise_waste_solutions_invoice(text: str) -> Optional[str]:
    """Earthwise Waste Solutions invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Earthwise Waste Solutions'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_earthwise_waste_solutions_invoice}

def _extract_southern_disposal_ar_invoice(text: str) -> Optional[str]:
    """Southern Disposal AR invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Southern Disposal AR'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_southern_disposal_ar_invoice}

def _extract_dan_s_sanitation_invoice(text: str) -> Optional[str]:
    """Dan's Sanitation invoice extractor"""
    match = re.search(r'Invoice\s*Number:?\s*(\d{6,8})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Dan\'s Sanitation'] = {'format': 'NNNNNNN', 'examples': ['9408565'], 'extract': _extract_dan_s_sanitation_invoice}

def _extract_ferrell_s_disposal_invoice(text: str) -> Optional[str]:
    """Ferrell's Disposal invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Ferrell\'s Disposal'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_ferrell_s_disposal_invoice}

def _extract_waste_eliminator_invoice(text: str) -> Optional[str]:
    """Waste Eliminator invoice extractor"""
    match = re.search(r'Invoice\s*#:?\s*(\d{5,7})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Waste Eliminator'] = {'format': 'NNNNNN', 'examples': ['239288'], 'extract': _extract_waste_eliminator_invoice}

def _extract_napa_recycling_invoice(text: str) -> Optional[str]:
    """Napa Recycling invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Napa Recycling'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_napa_recycling_invoice}

def _extract_city_of_snellville_invoice(text: str) -> Optional[str]:
    """City of Snellville invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['City of Snellville'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_city_of_snellville_invoice}

def _extract_texas_pride_disposal_invoice(text: str) -> Optional[str]:
    """Texas Pride Disposal invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Texas Pride Disposal'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_texas_pride_disposal_invoice}

def _extract_city_of_lakeland_fl_invoice(text: str) -> Optional[str]:
    """City of Lakeland FL invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['City of Lakeland FL'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_city_of_lakeland_fl_invoice}

def _extract_city_of_temple_tx_invoice(text: str) -> Optional[str]:
    """City of Temple TX invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['City of Temple TX'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_city_of_temple_tx_invoice}

def _extract_choice_waste_services_invoice(text: str) -> Optional[str]:
    """Choice Waste Services invoice extractor"""
    match = re.search(r'Invoice\s*#:?\s*(\d{5,7})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Choice Waste Services'] = {'format': 'NNNNNN', 'examples': ['846337'], 'extract': _extract_choice_waste_services_invoice}

def _extract_marin_sanitary_invoice(text: str) -> Optional[str]:
    """Marin Sanitary invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Marin Sanitary'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_marin_sanitary_invoice}

def _extract_wayne_county_utah_invoice(text: str) -> Optional[str]:
    """Wayne County Utah invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Wayne County Utah'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_wayne_county_utah_invoice}

def _extract_complete_solutions_sourcing_invoice(text: str) -> Optional[str]:
    """Complete Solutions & Sourcing invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Complete Solutions & Sourcing'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_complete_solutions_sourcing_invoice}

def _extract_t_mac_inc_invoice(text: str) -> Optional[str]:
    """T-Mac Inc invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['T-Mac Inc'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_t_mac_inc_invoice}

def _extract_wm_compactor_solutions_invoice(text: str) -> Optional[str]:
    """WM Compactor Solutions invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['WM Compactor Solutions'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_wm_compactor_solutions_invoice}

def _extract_u_i_sanitation_invoice(text: str) -> Optional[str]:
    """U & I Sanitation invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['U & I Sanitation'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_u_i_sanitation_invoice}

def _extract_thompson_s_sanitary_service_invoice(text: str) -> Optional[str]:
    """Thompson's Sanitary Service invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Thompson\'s Sanitary Service'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_thompson_s_sanitary_service_invoice}

def _extract_swinger_sanitation_invoice(text: str) -> Optional[str]:
    """Swinger Sanitation invoice extractor"""
    match = re.search(r'Invoice\s*Number:?\s*(\d{7,9})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Swinger Sanitation'] = {'format': 'NNNNNNNN', 'examples': ['10117677'], 'extract': _extract_swinger_sanitation_invoice}

def _extract_c_s_disposal_invoice(text: str) -> Optional[str]:
    """C&S Disposal invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['C&S Disposal'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_c_s_disposal_invoice}

def _extract_city_of_mont_belvieu_invoice(text: str) -> Optional[str]:
    """City of Mont Belvieu invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['City of Mont Belvieu'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_city_of_mont_belvieu_invoice}

def _extract_pellitteri_invoice(text: str) -> Optional[str]:
    """Pellitteri invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Pellitteri'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_pellitteri_invoice}

def _extract_hale_county_public_works_invoice(text: str) -> Optional[str]:
    """Hale County Public Works invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Hale County Public Works'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_hale_county_public_works_invoice}

def _extract_city_of_somerset_invoice(text: str) -> Optional[str]:
    """City of Somerset invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['City of Somerset'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_city_of_somerset_invoice}

def _extract_alpha_waste_disposal_invoice(text: str) -> Optional[str]:
    """Alpha Waste Disposal invoice extractor"""
    match = re.search(r'Invoice\s*Number:?\s*(\d{4,6})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Alpha Waste Disposal'] = {'format': 'NNNNN', 'examples': ['55056'], 'extract': _extract_alpha_waste_disposal_invoice}

def _extract_mills_brothers_invoice(text: str) -> Optional[str]:
    """Mills Brothers invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Mills Brothers'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_mills_brothers_invoice}

def _extract_american_sanitation_invoice(text: str) -> Optional[str]:
    """American Sanitation invoice extractor"""
    match = re.search(r'Invoice\s*#:?\s*(\d{5,7})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['American Sanitation'] = {'format': 'NNNNNN', 'examples': ['154054'], 'extract': _extract_american_sanitation_invoice}

def _extract_advance_machine_hydraulic_invoice(text: str) -> Optional[str]:
    """Advance Machine & Hydraulic invoice extractor"""
    match = re.search(r'Invoice\s*No\.?:?\s*(\d{4,6})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Advance Machine & Hydraulic'] = {'format': 'NNNNN', 'examples': ['10360'], 'extract': _extract_advance_machine_hydraulic_invoice}

def _extract_waste_resources_gardena_invoice(text: str) -> Optional[str]:
    """Waste Resources Gardena invoice extractor"""
    match = re.search(r'Invoice\s*No\.?:?\s*(\d{9,11})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Waste Resources Gardena'] = {'format': 'NNNNNNNNNN', 'examples': ['0003798894'], 'extract': _extract_waste_resources_gardena_invoice}

def _extract_cards_mo_invoice(text: str) -> Optional[str]:
    """Cards Mo invoice extractor"""
    match = re.search(r'Invoice\s*#:?\s*(\d{6,8})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Cards Mo'] = {'format': 'NNNNNNN', 'examples': ['1404622'], 'extract': _extract_cards_mo_invoice}

def _extract_texas_commercial_waste_invoice(text: str) -> Optional[str]:
    """Texas Commercial Waste invoice extractor"""
    match = re.search(r'Invoice\s*#:?\s*(\d{5,7})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Texas Commercial Waste'] = {'format': 'NNNNNN', 'examples': ['477907'], 'extract': _extract_texas_commercial_waste_invoice}

def _extract_tahoe_truckee_sierra_disposal_invoice(text: str) -> Optional[str]:
    """Tahoe Truckee Sierra Disposal invoice extractor"""
    match = re.search(r'Invoice\s*No\.?:?\s*(\d{9,11})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Tahoe Truckee Sierra Disposal'] = {'format': 'NNNNNNNNNN', 'examples': ['0000956464'], 'extract': _extract_tahoe_truckee_sierra_disposal_invoice}

def _extract_laveine_sanitation_invoice(text: str) -> Optional[str]:
    """LaVeine Sanitation invoice extractor"""
    match = re.search(r'Invoice\s*#:?\s*(\d{4,6})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['LaVeine Sanitation'] = {'format': 'NNNNN', 'examples': ['90376'], 'extract': _extract_laveine_sanitation_invoice}

def _extract_tri_county_industries_invoice(text: str) -> Optional[str]:
    """Tri-County Industries invoice extractor"""
    match = re.search(r'Invoice\s*Number:?\s*(\d{6,8})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Tri-County Industries'] = {'format': 'NNNNNNN', 'examples': ['1813043'], 'extract': _extract_tri_county_industries_invoice}

def _extract_barbarino_disposal_invoice(text: str) -> Optional[str]:
    """Barbarino Disposal invoice extractor"""
    match = re.search(r'Invoice\s*Number:?\s*(\d{6,8})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Barbarino Disposal'] = {'format': 'NNNNNNN', 'examples': ['2734680'], 'extract': _extract_barbarino_disposal_invoice}

def _extract_nei_pennsylvania_invoice(text: str) -> Optional[str]:
    """NEI Pennsylvania invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['NEI Pennsylvania'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_nei_pennsylvania_invoice}

def _extract_jay_mecham_s_invoice(text: str) -> Optional[str]:
    """Jay Mecham's invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Jay Mecham\'s'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_jay_mecham_s_invoice}

def _extract_star_waste_invoice(text: str) -> Optional[str]:
    """Star Waste invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Star Waste'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_star_waste_invoice}

def _extract_k_town_disposal_invoice(text: str) -> Optional[str]:
    """K-Town Disposal invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['K-Town Disposal'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_k_town_disposal_invoice}

def _extract_city_sanitary_service_invoice(text: str) -> Optional[str]:
    """City Sanitary Service invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['City Sanitary Service'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_city_sanitary_service_invoice}

def _extract_shamrock_waste_invoice(text: str) -> Optional[str]:
    """Shamrock Waste invoice extractor"""
    match = re.search(r'Invoice\s*Number:?\s*(\d{9,11})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Shamrock Waste'] = {'format': 'NNNNNNNNNN', 'examples': ['2509251219'], 'extract': _extract_shamrock_waste_invoice}

def _extract_arrowhead_waste_invoice(text: str) -> Optional[str]:
    """Arrowhead Waste invoice extractor"""
    match = re.search(r'Invoice\s*Number:?\s*(\d{6,8})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Arrowhead Waste'] = {'format': 'NNNNNNN', 'examples': ['9161456'], 'extract': _extract_arrowhead_waste_invoice}

def _extract_basin_haulage_invoice(text: str) -> Optional[str]:
    """Basin Haulage invoice extractor"""
    match = re.search(r'Invoice\s*#?:?\s*([A-Z]{1,3}[-]?\d{4,7})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Basin Haulage'] = {'format': 'XX-NNNN', 'examples': ['FW78792'], 'extract': _extract_basin_haulage_invoice}

def _extract_bavarian_waste_invoice(text: str) -> Optional[str]:
    """Bavarian Waste invoice extractor"""
    match = re.search(r'Invoice\s*#:?\s*(\d{5,7})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Bavarian Waste'] = {'format': 'NNNNNN', 'examples': ['302234'], 'extract': _extract_bavarian_waste_invoice}

def _extract_american_reclamation_invoice(text: str) -> Optional[str]:
    """American Reclamation invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['American Reclamation'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_american_reclamation_invoice}

def _extract_mcud_manatee_invoice(text: str) -> Optional[str]:
    """MCUD Manatee invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['MCUD Manatee'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_mcud_manatee_invoice}

def _extract_city_of_wolf_point_invoice(text: str) -> Optional[str]:
    """City of Wolf Point invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['City of Wolf Point'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_city_of_wolf_point_invoice}

def _extract_lex_serv_invoice(text: str) -> Optional[str]:
    """Lex Serv invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Lex Serv'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_lex_serv_invoice}

def _extract_stewart_sanitation_invoice(text: str) -> Optional[str]:
    """Stewart Sanitation invoice extractor"""
    match = re.search(r'Invoice\s*#:?\s*(\d{9,11})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Stewart Sanitation'] = {'format': 'NNNNNNNNNN', 'examples': ['0000900820'], 'extract': _extract_stewart_sanitation_invoice}

def _extract_georgia_waste_systems_invoice(text: str) -> Optional[str]:
    """Georgia Waste Systems invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Georgia Waste Systems'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_georgia_waste_systems_invoice}

def _extract_rad_curbside_invoice(text: str) -> Optional[str]:
    """RAD Curbside invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['RAD Curbside'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_rad_curbside_invoice}

def _extract_lake_disposal_service_invoice(text: str) -> Optional[str]:
    """Lake Disposal Service invoice extractor"""
    match = re.search(r'Invoice\s*#:?\s*(\d{5,7})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Lake Disposal Service'] = {'format': 'NNNNNN', 'examples': ['123117'], 'extract': _extract_lake_disposal_service_invoice}

def _extract_city_of_ketchikan_invoice(text: str) -> Optional[str]:
    """City of Ketchikan invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['City of Ketchikan'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_city_of_ketchikan_invoice}

def _extract_humboldt_county_landfill_invoice(text: str) -> Optional[str]:
    """Humboldt County Landfill invoice extractor"""
    match = re.search(r'Invoice\s*#:?\s*(\d{4,6})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Humboldt County Landfill'] = {'format': 'NNNNN', 'examples': ['13895'], 'extract': _extract_humboldt_county_landfill_invoice}

def _extract_solid_rock_waste_invoice(text: str) -> Optional[str]:
    """Solid Rock Waste invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Solid Rock Waste'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_solid_rock_waste_invoice}

def _extract_t_g_sanitation_invoice(text: str) -> Optional[str]:
    """T & G Sanitation invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['T & G Sanitation'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_t_g_sanitation_invoice}

def _extract_american_waste_control_invoice(text: str) -> Optional[str]:
    """American Waste Control invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['American Waste Control'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_american_waste_control_invoice}

def _extract_island_disposal_invoice(text: str) -> Optional[str]:
    """Island Disposal invoice extractor"""
    match = re.search(r'Invoice\s*Number:?\s*(\d{9,11})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Island Disposal'] = {'format': 'NNNNNNNNNN', 'examples': ['2509016919'], 'extract': _extract_island_disposal_invoice}

def _extract_olson_sanitation_invoice(text: str) -> Optional[str]:
    """Olson Sanitation invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Olson Sanitation'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_olson_sanitation_invoice}

def _extract_oregon_city_garbage_invoice(text: str) -> Optional[str]:
    """Oregon City Garbage invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Oregon City Garbage'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_oregon_city_garbage_invoice}

def _extract_always_green_recycling_invoice(text: str) -> Optional[str]:
    """Always Green Recycling invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Always Green Recycling'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_always_green_recycling_invoice}

def _extract_happy_can_disposal_invoice(text: str) -> Optional[str]:
    """Happy Can Disposal invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Happy Can Disposal'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_happy_can_disposal_invoice}

def _extract_res_waste_invoice(text: str) -> Optional[str]:
    """RES Waste invoice extractor"""
    match = re.search(r'Invoice\s*#:?\s*(\d{5,7})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['RES Waste'] = {'format': 'NNNNNN', 'examples': ['319443'], 'extract': _extract_res_waste_invoice}

def _extract_reworld_invoice(text: str) -> Optional[str]:
    """Reworld invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Reworld'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_reworld_invoice}

def _extract_trash_rangers_invoice(text: str) -> Optional[str]:
    """Trash Rangers invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Trash Rangers'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_trash_rangers_invoice}

def _extract_msc_industries_invoice(text: str) -> Optional[str]:
    """MSC Industries invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['MSC Industries'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_msc_industries_invoice}

def _extract_wingfield_service_invoice(text: str) -> Optional[str]:
    """Wingfield Service invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Wingfield Service'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_wingfield_service_invoice}

def _extract_a_j_trash_invoice(text: str) -> Optional[str]:
    """A&J Trash invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['A&J Trash'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_a_j_trash_invoice}

def _extract_city_of_rowlett_invoice(text: str) -> Optional[str]:
    """City of Rowlett invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['City of Rowlett'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_city_of_rowlett_invoice}

def _extract_walters_sanitary_service_invoice(text: str) -> Optional[str]:
    """Walters Sanitary Service invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Walters Sanitary Service'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_walters_sanitary_service_invoice}

def _extract_american_resource_management_invoice(text: str) -> Optional[str]:
    """American Resource Management invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['American Resource Management'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_american_resource_management_invoice}

def _extract_save_that_stuff_invoice(text: str) -> Optional[str]:
    """Save That Stuff invoice extractor"""
    match = re.search(r'Invoice\s*Number:?\s*(\d{5,7})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Save That Stuff'] = {'format': 'NNNNNN', 'examples': ['164145'], 'extract': _extract_save_that_stuff_invoice}

def _extract_city_of_conyers_invoice(text: str) -> Optional[str]:
    """City of Conyers invoice extractor"""
    match = re.search(r'Invoice\s*Number:?\s*(\d{5,7})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['City of Conyers'] = {'format': 'NNNNNN', 'examples': ['246190'], 'extract': _extract_city_of_conyers_invoice}

def _extract_cloquet_sanitary_invoice(text: str) -> Optional[str]:
    """Cloquet Sanitary invoice extractor"""
    match = re.search(r'Invoice\s*No\.?:?\s*(\d{5,7})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Cloquet Sanitary'] = {'format': 'NNNNNN', 'examples': ['926239'], 'extract': _extract_cloquet_sanitary_invoice}

def _extract_quincy_recycling_invoice(text: str) -> Optional[str]:
    """Quincy Recycling invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Quincy Recycling'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_quincy_recycling_invoice}

def _extract_russell_county_sanitation_invoice(text: str) -> Optional[str]:
    """Russell County Sanitation invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Russell County Sanitation'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_russell_county_sanitation_invoice}

def _extract_nisswa_sanitation_invoice(text: str) -> Optional[str]:
    """Nisswa Sanitation invoice extractor"""
    match = re.search(r'Invoice\s*Number:?\s*(\d{6,8})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Nisswa Sanitation'] = {'format': 'NNNNNNN', 'examples': ['3174300'], 'extract': _extract_nisswa_sanitation_invoice}

def _extract_jackson_county_solid_waste_invoice(text: str) -> Optional[str]:
    """Jackson County Solid Waste invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Jackson County Solid Waste'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_jackson_county_solid_waste_invoice}

def _extract_city_of_bardstown_invoice(text: str) -> Optional[str]:
    """City of Bardstown invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['City of Bardstown'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_city_of_bardstown_invoice}

def _extract_maverick_waste_invoice(text: str) -> Optional[str]:
    """Maverick Waste invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Maverick Waste'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_maverick_waste_invoice}

def _extract_gardner_disposal_service_invoice(text: str) -> Optional[str]:
    """Gardner Disposal Service invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Gardner Disposal Service'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_gardner_disposal_service_invoice}

def _extract_good_s_disposal_invoice(text: str) -> Optional[str]:
    """Good's Disposal invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Good\'s Disposal'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_good_s_disposal_invoice}

def _extract_southeast_waste_disposal_invoice(text: str) -> Optional[str]:
    """Southeast Waste Disposal invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Southeast Waste Disposal'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_southeast_waste_disposal_invoice}

def _extract_gmen_environmental_invoice(text: str) -> Optional[str]:
    """Gmen Environmental invoice extractor"""
    match = re.search(r'Invoice\s*Number:?\s*(\d{5,7})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Gmen Environmental'] = {'format': 'NNNNNN', 'examples': ['509300'], 'extract': _extract_gmen_environmental_invoice}

def _extract_pride_disposal_invoice(text: str) -> Optional[str]:
    """PRIDE Disposal invoice extractor"""
    match = re.search(r'Invoice\s*#:?\s*(\d{9,11})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['PRIDE Disposal'] = {'format': 'NNNNNNNNNN', 'examples': ['0003991182'], 'extract': _extract_pride_disposal_invoice}

def _extract_tropical_trash_invoice(text: str) -> Optional[str]:
    """Tropical Trash invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Tropical Trash'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_tropical_trash_invoice}

def _extract_pike_county_solid_waste_invoice(text: str) -> Optional[str]:
    """Pike County Solid Waste invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Pike County Solid Waste'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_pike_county_solid_waste_invoice}

def _extract_the_trash_guys_invoice(text: str) -> Optional[str]:
    """The Trash Guys invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['The Trash Guys'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_the_trash_guys_invoice}

def _extract_vista_recycling_invoice(text: str) -> Optional[str]:
    """Vista Recycling invoice extractor"""
    match = re.search(r'Invoice\s*Number:?\s*(\d{4,6})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Vista Recycling'] = {'format': 'NNNNN', 'examples': ['74969'], 'extract': _extract_vista_recycling_invoice}

def _extract_ameriwaste_invoice(text: str) -> Optional[str]:
    """Ameriwaste invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Ameriwaste'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_ameriwaste_invoice}

def _extract_charlie_s_waste_invoice(text: str) -> Optional[str]:
    """Charlie's Waste invoice extractor"""
    match = re.search(r'Invoice\s*No\.?:?\s*(\d{9,11})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Charlie\'s Waste'] = {'format': 'NNNNNNNNNN', 'examples': ['0000399838'], 'extract': _extract_charlie_s_waste_invoice}

def _extract_city_of_sidney_invoice(text: str) -> Optional[str]:
    """City of Sidney invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['City of Sidney'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_city_of_sidney_invoice}

def _extract_iv_waste_invoice(text: str) -> Optional[str]:
    """IV Waste invoice extractor"""
    match = re.search(r'Invoice\s*No\.?:?\s*(\d{9,11})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['IV Waste'] = {'format': 'NNNNNNNNNN', 'examples': ['0000215332'], 'extract': _extract_iv_waste_invoice}

def _extract_miami_waste_paper_invoice(text: str) -> Optional[str]:
    """Miami Waste Paper invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Miami Waste Paper'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_miami_waste_paper_invoice}

def _extract_united_states_disposal_invoice(text: str) -> Optional[str]:
    """United States Disposal invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['United States Disposal'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_united_states_disposal_invoice}

def _extract_city_of_lewiston_invoice(text: str) -> Optional[str]:
    """City of Lewiston invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['City of Lewiston'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_city_of_lewiston_invoice}

def _extract_north_country_disposal_invoice(text: str) -> Optional[str]:
    """North Country Disposal invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['North Country Disposal'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_north_country_disposal_invoice}

def _extract_p_m_reis_trucking_invoice(text: str) -> Optional[str]:
    """P&M Reis Trucking invoice extractor"""
    match = re.search(r'Invoice\s*Number:?\s*(\d{6,8})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['P&M Reis Trucking'] = {'format': 'NNNNNNN', 'examples': ['9441229'], 'extract': _extract_p_m_reis_trucking_invoice}

def _extract_speedy_dump_invoice(text: str) -> Optional[str]:
    """Speedy Dump invoice extractor"""
    match = re.search(r'INV[-\s]?(\d{4,6})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Speedy Dump'] = {'format': 'INV-NNNNN', 'examples': ['15918'], 'extract': _extract_speedy_dump_invoice}

def _extract_hughes_trash_removal_invoice(text: str) -> Optional[str]:
    """Hughes Trash Removal invoice extractor"""
    match = re.search(r'Invoice\s*No\.?:?\s*(\d{7,9})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Hughes Trash Removal'] = {'format': 'NNNNNNNN', 'examples': ['61180834'], 'extract': _extract_hughes_trash_removal_invoice}

def _extract_franklin_pallet_invoice(text: str) -> Optional[str]:
    """Franklin Pallet invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Franklin Pallet'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_franklin_pallet_invoice}

def _extract_green_river_waste_invoice(text: str) -> Optional[str]:
    """Green River Waste invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Green River Waste'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_green_river_waste_invoice}

def _extract_mccullough_rubbish_invoice(text: str) -> Optional[str]:
    """McCullough Rubbish invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['McCullough Rubbish'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_mccullough_rubbish_invoice}

def _extract_kalamazoo_transfer_station_invoice(text: str) -> Optional[str]:
    """Kalamazoo Transfer Station invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Kalamazoo Transfer Station'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_kalamazoo_transfer_station_invoice}

def _extract_kootenai_county_solid_waste_invoice(text: str) -> Optional[str]:
    """Kootenai County Solid Waste invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Kootenai County Solid Waste'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_kootenai_county_solid_waste_invoice}

def _extract_city_of_culver_city_invoice(text: str) -> Optional[str]:
    """City of Culver City invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['City of Culver City'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_city_of_culver_city_invoice}

def _extract_suburban_waste_services_invoice(text: str) -> Optional[str]:
    """Suburban Waste Services invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Suburban Waste Services'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_suburban_waste_services_invoice}

def _extract_black_earth_compost_invoice(text: str) -> Optional[str]:
    """Black Earth Compost invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Black Earth Compost'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_black_earth_compost_invoice}

def _extract_a_c_waste_collection_invoice(text: str) -> Optional[str]:
    """A&C Waste Collection invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['A&C Waste Collection'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_a_c_waste_collection_invoice}

def _extract_city_of_tulsa_invoice(text: str) -> Optional[str]:
    """City of Tulsa invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['City of Tulsa'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_city_of_tulsa_invoice}

def _extract_a_1_disposal_invoice(text: str) -> Optional[str]:
    """A-1 Disposal invoice extractor"""
    match = re.search(r'Inv\s*#:?\s*(\d{5,7})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['A-1 Disposal'] = {'format': 'NNNNNN', 'examples': ['272100'], 'extract': _extract_a_1_disposal_invoice}

def _extract_gilton_solid_waste_invoice(text: str) -> Optional[str]:
    """Gilton Solid Waste invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Gilton Solid Waste'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_gilton_solid_waste_invoice}

def _extract_native_dynamics_invoice(text: str) -> Optional[str]:
    """Native Dynamics invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Native Dynamics'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_native_dynamics_invoice}

def _extract_irow_invoice(text: str) -> Optional[str]:
    """IROW invoice extractor"""
    match = re.search(r'Invoice\s*#:?\s*(\d{5,7})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['IROW'] = {'format': 'NNNNNN', 'examples': ['323425'], 'extract': _extract_irow_invoice}

def _extract_gresham_sanitary_service_invoice(text: str) -> Optional[str]:
    """Gresham Sanitary Service invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Gresham Sanitary Service'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_gresham_sanitary_service_invoice}

def _extract_disposal_services_llc_invoice(text: str) -> Optional[str]:
    """Disposal Services LLC invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Disposal Services LLC'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_disposal_services_llc_invoice}

def _extract_waterman_recycling_invoice(text: str) -> Optional[str]:
    """Waterman Recycling invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Waterman Recycling'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_waterman_recycling_invoice}

def _extract_westside_waste_management_invoice(text: str) -> Optional[str]:
    """Westside Waste Management invoice extractor"""
    match = re.search(r'Invoice\s*#:?\s*(\d{4,6})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Westside Waste Management'] = {'format': 'NNNNN', 'examples': ['78316'], 'extract': _extract_westside_waste_management_invoice}

def _extract_tds_llc_invoice(text: str) -> Optional[str]:
    """TDS LLC invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['TDS LLC'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_tds_llc_invoice}

def _extract_timmons_waste_service_invoice(text: str) -> Optional[str]:
    """Timmons Waste Service invoice extractor"""
    match = re.search(r'Invoice\s*Number:?\s*(\d{6,8})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Timmons Waste Service'] = {'format': 'NNNNNNN', 'examples': ['2743803'], 'extract': _extract_timmons_waste_service_invoice}

def _extract_treasure_coast_recycling_invoice(text: str) -> Optional[str]:
    """Treasure Coast Recycling invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Treasure Coast Recycling'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_treasure_coast_recycling_invoice}

def _extract_city_of_tracy_invoice(text: str) -> Optional[str]:
    """City of Tracy invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['City of Tracy'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_city_of_tracy_invoice}

def _extract_agri_cycle_invoice(text: str) -> Optional[str]:
    """Agri-Cycle invoice extractor"""
    match = re.search(r'Invoice\s*No\.?:?\s*(\d{9,11})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Agri-Cycle'] = {'format': 'NNNNNNNNNN', 'examples': ['0000044018'], 'extract': _extract_agri_cycle_invoice}

def _extract_bright_disposal_services_invoice(text: str) -> Optional[str]:
    """Bright Disposal Services invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Bright Disposal Services'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_bright_disposal_services_invoice}

def _extract_serv_wel_disposal_invoice(text: str) -> Optional[str]:
    """Serv-Wel Disposal invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Serv-Wel Disposal'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_serv_wel_disposal_invoice}

def _extract_douglas_disposal_invoice(text: str) -> Optional[str]:
    """Douglas Disposal invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Douglas Disposal'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_douglas_disposal_invoice}

def _extract_city_of_rockhill_invoice(text: str) -> Optional[str]:
    """City of Rockhill invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['City of Rockhill'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_city_of_rockhill_invoice}

def _extract_apex_recycling_disposal_invoice(text: str) -> Optional[str]:
    """Apex Recycling & Disposal invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Apex Recycling & Disposal'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_apex_recycling_disposal_invoice}

def _extract_all_states_services_invoice(text: str) -> Optional[str]:
    """All States Services invoice extractor"""
    match = re.search(r'Invoice\s*No\.?:?\s*(\d{6,8})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['All States Services'] = {'format': 'NNNNNNN', 'examples': ['0243113'], 'extract': _extract_all_states_services_invoice}

def _extract_ogborne_hauling_invoice(text: str) -> Optional[str]:
    """Ogborne Hauling invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Ogborne Hauling'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_ogborne_hauling_invoice}

def _extract_city_of_mount_vernon_wa_invoice(text: str) -> Optional[str]:
    """City of Mount Vernon WA invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['City of Mount Vernon WA'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_city_of_mount_vernon_wa_invoice}

def _extract_rightaway_rolloff_invoice(text: str) -> Optional[str]:
    """RightAway RollOff invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['RightAway RollOff'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_rightaway_rolloff_invoice}

def _extract_friends_garbage_invoice(text: str) -> Optional[str]:
    """Friends Garbage invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Friends Garbage'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_friends_garbage_invoice}

def _extract_innovative_trash_service_invoice(text: str) -> Optional[str]:
    """Innovative Trash Service invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Innovative Trash Service'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_innovative_trash_service_invoice}

def _extract_j_jay_services_invoice(text: str) -> Optional[str]:
    """J&Jay Services invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['J&Jay Services'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_j_jay_services_invoice}

def _extract_a1_porta_potty_invoice(text: str) -> Optional[str]:
    """A1 Porta Potty invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['A1 Porta Potty'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_a1_porta_potty_invoice}

def _extract_grogan_waste_invoice(text: str) -> Optional[str]:
    """Grogan Waste invoice extractor"""
    match = re.search(r'Invoice\s*#:?\s*(\d{4,6})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Grogan Waste'] = {'format': 'NNNNN', 'examples': ['72208'], 'extract': _extract_grogan_waste_invoice}

def _extract_city_of_windcrest_invoice(text: str) -> Optional[str]:
    """City of Windcrest invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['City of Windcrest'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_city_of_windcrest_invoice}

def _extract_golden_valley_disposal_invoice(text: str) -> Optional[str]:
    """Golden Valley Disposal invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Golden Valley Disposal'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_golden_valley_disposal_invoice}

def _extract_guido_s_services_invoice(text: str) -> Optional[str]:
    """Guido's Services invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Guido\'s Services'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_guido_s_services_invoice}

def _extract_valley_waste_service_invoice(text: str) -> Optional[str]:
    """Valley Waste Service invoice extractor"""
    match = re.search(r'Invoice\s*Number:?\s*(\d{6,8})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Valley Waste Service'] = {'format': 'NNNNNNN', 'examples': ['1035269'], 'extract': _extract_valley_waste_service_invoice}

def _extract_bgl_suburban_garbage_invoice(text: str) -> Optional[str]:
    """BGL Suburban Garbage invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['BGL Suburban Garbage'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_bgl_suburban_garbage_invoice}

def _extract_brandt_s_sanitary_invoice(text: str) -> Optional[str]:
    """Brandt's Sanitary invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Brandt\'s Sanitary'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_brandt_s_sanitary_invoice}

def _extract_roll_off_chick_invoice(text: str) -> Optional[str]:
    """Roll-Off Chick invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Roll-Off Chick'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_roll_off_chick_invoice}

def _extract_real_waste_solutions_invoice(text: str) -> Optional[str]:
    """Real Waste Solutions invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Real Waste Solutions'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_real_waste_solutions_invoice}

def _extract_k_k_sanitation_invoice(text: str) -> Optional[str]:
    """K & K Sanitation invoice extractor"""
    match = re.search(r'Invoice\s*Number:?\s*(\d{9,11})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['K & K Sanitation'] = {'format': 'NNNNNNNNNN', 'examples': ['2510290761'], 'extract': _extract_k_k_sanitation_invoice}

def _extract_richland_county_landfill_invoice(text: str) -> Optional[str]:
    """Richland County Landfill invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Richland County Landfill'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_richland_county_landfill_invoice}

def _extract_les_s_sanitation_invoice(text: str) -> Optional[str]:
    """Les's Sanitation invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Les\'s Sanitation'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_les_s_sanitation_invoice}

def _extract_roadrunner_rubbish_invoice(text: str) -> Optional[str]:
    """Roadrunner Rubbish invoice extractor"""
    match = re.search(r'Invoice\s*#:?\s*(\d{9,11})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Roadrunner Rubbish'] = {'format': 'NNNNNNNNNN', 'examples': ['2510152102'], 'extract': _extract_roadrunner_rubbish_invoice}

def _extract_advance_disposal_invoice(text: str) -> Optional[str]:
    """Advance Disposal invoice extractor"""
    match = re.search(r'Invoice\s*Number:?\s*(\d{9,11})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Advance Disposal'] = {'format': 'NNNNNNNNNN', 'examples': ['2601021317'], 'extract': _extract_advance_disposal_invoice}

def _extract_waste_masters_invoice(text: str) -> Optional[str]:
    """Waste Masters invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Waste Masters'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_waste_masters_invoice}

def _extract_pacific_sanitation_co_invoice(text: str) -> Optional[str]:
    """Pacific Sanitation Co invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Pacific Sanitation Co'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_pacific_sanitation_co_invoice}

def _extract_overton_recycling_invoice(text: str) -> Optional[str]:
    """Overton Recycling invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Overton Recycling'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_overton_recycling_invoice}

def _extract_absolute_waste_invoice(text: str) -> Optional[str]:
    """Absolute Waste invoice extractor"""
    match = re.search(r'Invoice\s*#:?\s*(\d{6,8})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Absolute Waste'] = {'format': 'NNNNNNN', 'examples': ['2102721'], 'extract': _extract_absolute_waste_invoice}

def _extract_troupe_waste_invoice(text: str) -> Optional[str]:
    """Troupe Waste invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Troupe Waste'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_troupe_waste_invoice}

def _extract_full_circle_recycling_invoice(text: str) -> Optional[str]:
    """Full Circle Recycling invoice extractor"""
    match = re.search(r'Invoice\s*#:?\s*(\d{4,6})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Full Circle Recycling'] = {'format': 'NNNNN', 'examples': ['46918'], 'extract': _extract_full_circle_recycling_invoice}

def _extract_salandro_refuse_invoice(text: str) -> Optional[str]:
    """Salandro Refuse invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Salandro Refuse'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_salandro_refuse_invoice}

def _extract_helgerson_property_maintenance_invoice(text: str) -> Optional[str]:
    """Helgerson Property Maintenance invoice extractor"""
    match = re.search(r'Invoice\s*No\.?:?\s*(\d{4,6})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Helgerson Property Maintenance'] = {'format': 'NNNNN', 'examples': ['11672'], 'extract': _extract_helgerson_property_maintenance_invoice}

def _extract_okon_recycling_invoice(text: str) -> Optional[str]:
    """Okon Recycling invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Okon Recycling'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_okon_recycling_invoice}

def _extract_waste_services_inc_invoice(text: str) -> Optional[str]:
    """Waste Services Inc invoice extractor"""
    match = re.search(r'Invoice\s*#:?\s*(\d{7,9})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Waste Services Inc'] = {'format': 'NNNNNNNN', 'examples': ['61100547'], 'extract': _extract_waste_services_inc_invoice}

def _extract_city_of_las_cruces_invoice(text: str) -> Optional[str]:
    """City of Las Cruces invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['City of Las Cruces'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_city_of_las_cruces_invoice}

def _extract_pinto_service_invoice(text: str) -> Optional[str]:
    """Pinto Service invoice extractor"""
    match = re.search(r'Invoice\s*Number:?\s*(\d{5,7})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Pinto Service'] = {'format': 'NNNNNN', 'examples': ['635637'], 'extract': _extract_pinto_service_invoice}

def _extract_city_of_durant_invoice(text: str) -> Optional[str]:
    """City of Durant invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['City of Durant'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_city_of_durant_invoice}

def _extract_kohlmorgan_hauling_invoice(text: str) -> Optional[str]:
    """Kohlmorgan Hauling invoice extractor"""
    match = re.search(r'Invoice\s*#:?\s*(\d{5,7})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Kohlmorgan Hauling'] = {'format': 'NNNNNN', 'examples': ['112627'], 'extract': _extract_kohlmorgan_hauling_invoice}

def _extract_fogle_s_invoice(text: str) -> Optional[str]:
    """Fogle's invoice extractor"""
    match = re.search(r'Invoice\s*Number:?\s*(\d{5,7})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Fogle\'s'] = {'format': 'NNNNNN', 'examples': ['279344'], 'extract': _extract_fogle_s_invoice}

def _extract_southern_oregon_sanitation_invoice(text: str) -> Optional[str]:
    """Southern Oregon Sanitation invoice extractor"""
    match = re.search(r'Invoice\s*Number:?\s*(\d{9,11})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Southern Oregon Sanitation'] = {'format': 'NNNNNNNNNN', 'examples': ['0725202575'], 'extract': _extract_southern_oregon_sanitation_invoice}

def _extract_two_men_and_a_junk_truck_invoice(text: str) -> Optional[str]:
    """Two Men and a Junk Truck invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Two Men and a Junk Truck'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_two_men_and_a_junk_truck_invoice}

def _extract_ns_disposal_invoice(text: str) -> Optional[str]:
    """NS Disposal invoice extractor"""
    match = re.search(r'Invoice\s*Number:?\s*(\d{4,6})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['NS Disposal'] = {'format': 'NNNNN', 'examples': ['41871'], 'extract': _extract_ns_disposal_invoice}

def _extract_roadrunner_sanitation_invoice(text: str) -> Optional[str]:
    """Roadrunner Sanitation invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Roadrunner Sanitation'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_roadrunner_sanitation_invoice}

def _extract_modern_disposal_invoice(text: str) -> Optional[str]:
    """Modern Disposal invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Modern Disposal'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_modern_disposal_invoice}

def _extract_wayn_o_s_disposal_service_invoice(text: str) -> Optional[str]:
    """Wayn-O's Disposal Service invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Wayn-O\'s Disposal Service'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_wayn_o_s_disposal_service_invoice}

def _extract_solid_waste_services_wv_invoice(text: str) -> Optional[str]:
    """Solid Waste Services WV invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Solid Waste Services WV'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_solid_waste_services_wv_invoice}

def _extract_marck_recycling_and_waste_invoice(text: str) -> Optional[str]:
    """Marck Recycling and Waste invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Marck Recycling and Waste'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_marck_recycling_and_waste_invoice}

def _extract_garland_county_landfill_invoice(text: str) -> Optional[str]:
    """Garland County Landfill invoice extractor"""
    match = re.search(r'Invoice\s*#:?\s*(\d{5,7})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Garland County Landfill'] = {'format': 'NNNNNN', 'examples': ['127527'], 'extract': _extract_garland_county_landfill_invoice}

def _extract_city_of_hidalgo_invoice(text: str) -> Optional[str]:
    """City of Hidalgo invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['City of Hidalgo'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_city_of_hidalgo_invoice}

def _extract_reed_maintenance_invoice(text: str) -> Optional[str]:
    """Reed Maintenance invoice extractor"""
    match = re.search(r'Invoice\s*No\.?:?\s*(\d{5,7})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Reed Maintenance'] = {'format': 'NNNNNN', 'examples': ['103866'], 'extract': _extract_reed_maintenance_invoice}

def _extract_olathe_kansas_invoice(text: str) -> Optional[str]:
    """Olathe Kansas invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Olathe Kansas'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_olathe_kansas_invoice}

def _extract_a_w_iron_metal_invoice(text: str) -> Optional[str]:
    """A&W Iron Metal invoice extractor"""
    match = re.search(r'Invoice\s*#:?\s*(\d{4,6})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['A&W Iron Metal'] = {'format': 'NNNNN', 'examples': ['15568'], 'extract': _extract_a_w_iron_metal_invoice}

def _extract_hmp_inc_invoice(text: str) -> Optional[str]:
    """HMP Inc invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['HMP Inc'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_hmp_inc_invoice}

def _extract_city_of_deerfield_beach_invoice(text: str) -> Optional[str]:
    """City of Deerfield Beach invoice extractor"""
    match = re.search(r'Invoice\s*No\.?:?\s*(\d{9,11})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['City of Deerfield Beach'] = {'format': 'NNNNNNNNNN', 'examples': ['0000196291'], 'extract': _extract_city_of_deerfield_beach_invoice}

def _extract_container_rental_co_invoice(text: str) -> Optional[str]:
    """Container Rental Co invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Container Rental Co'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_container_rental_co_invoice}

def _extract_texas_dumpsters_invoice(text: str) -> Optional[str]:
    """Texas Dumpsters invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Texas Dumpsters'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_texas_dumpsters_invoice}

def _extract_mds_waste_invoice(text: str) -> Optional[str]:
    """MDS Waste invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['MDS Waste'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_mds_waste_invoice}

def _extract_elite_recycling_invoice(text: str) -> Optional[str]:
    """Elite Recycling invoice extractor"""
    match = re.search(r'Invoice\s*No\.?:?\s*(\d{6,8})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Elite Recycling'] = {'format': 'NNNNNNN', 'examples': ['1504121'], 'extract': _extract_elite_recycling_invoice}

def _extract_great_waste_invoice(text: str) -> Optional[str]:
    """Great Waste invoice extractor"""
    match = re.search(r'Invoice\s*Number:?\s*(\d{5,7})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Great Waste'] = {'format': 'NNNNNN', 'examples': ['607205'], 'extract': _extract_great_waste_invoice}

def _extract_smurfit_invoice(text: str) -> Optional[str]:
    """Smurfit invoice extractor"""
    match = re.search(r'Invoice\s*No\.?:?\s*(\d{9,11})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Smurfit'] = {'format': 'NNNNNNNNNN', 'examples': ['4475914729'], 'extract': _extract_smurfit_invoice}

def _extract_pak_rite_rentals_invoice(text: str) -> Optional[str]:
    """Pak Rite Rentals invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Pak Rite Rentals'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_pak_rite_rentals_invoice}

def _extract_woodward_s_disposal_invoice(text: str) -> Optional[str]:
    """Woodward's Disposal invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Woodward\'s Disposal'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_woodward_s_disposal_invoice}

def _extract_econo_waste_invoice(text: str) -> Optional[str]:
    """Econo Waste invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Econo Waste'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_econo_waste_invoice}

def _extract_dyersburg_gas_water_invoice(text: str) -> Optional[str]:
    """Dyersburg Gas & Water invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Dyersburg Gas & Water'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_dyersburg_gas_water_invoice}

def _extract_efficient_roll_off_recycling_invoice(text: str) -> Optional[str]:
    """Efficient Roll-Off & Recycling invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Efficient Roll-Off & Recycling'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_efficient_roll_off_recycling_invoice}

def _extract_city_of_winfield_invoice(text: str) -> Optional[str]:
    """City of Winfield invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['City of Winfield'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_city_of_winfield_invoice}

def _extract_moler_sanitation_invoice(text: str) -> Optional[str]:
    """Moler Sanitation invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Moler Sanitation'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_moler_sanitation_invoice}

def _extract_volunteer_disposal_west_invoice(text: str) -> Optional[str]:
    """Volunteer Disposal West invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Volunteer Disposal West'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_volunteer_disposal_west_invoice}

def _extract_city_of_fargo_invoice(text: str) -> Optional[str]:
    """City of Fargo invoice extractor"""
    match = re.search(r'Invoice\s*No\.?:?\s*(\d{5,7})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['City of Fargo'] = {'format': 'NNNNNN', 'examples': ['479013'], 'extract': _extract_city_of_fargo_invoice}

def _extract_lusk_disposal_invoice(text: str) -> Optional[str]:
    """Lusk Disposal invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Lusk Disposal'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_lusk_disposal_invoice}

def _extract_raekar_invoice(text: str) -> Optional[str]:
    """RaeKar invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['RaeKar'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_raekar_invoice}

def _extract_action_trucking_invoice(text: str) -> Optional[str]:
    """Action Trucking invoice extractor"""
    match = re.search(r'Invoice\s*#:?\s*(\d{4,6})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Action Trucking'] = {'format': 'NNNNN', 'examples': ['30262'], 'extract': _extract_action_trucking_invoice}

def _extract_g2_revolution_invoice(text: str) -> Optional[str]:
    """G2 Revolution invoice extractor"""
    match = re.search(r'Invoice\s*No\.?:?\s*(\d{4,6})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['G2 Revolution'] = {'format': 'NNNNN', 'examples': ['57575'], 'extract': _extract_g2_revolution_invoice}

def _extract_tovar_equipment_invoice(text: str) -> Optional[str]:
    """Tovar Equipment invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Tovar Equipment'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_tovar_equipment_invoice}

def _extract_lakeland_disposal_wi_invoice(text: str) -> Optional[str]:
    """Lakeland Disposal WI invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Lakeland Disposal WI'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_lakeland_disposal_wi_invoice}

def _extract_whites_sanitation_invoice(text: str) -> Optional[str]:
    """Whites Sanitation invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Whites Sanitation'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_whites_sanitation_invoice}

def _extract_city_of_huron_invoice(text: str) -> Optional[str]:
    """City of Huron invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['City of Huron'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_city_of_huron_invoice}

def _extract_chesapeake_waste_invoice(text: str) -> Optional[str]:
    """Chesapeake Waste invoice extractor"""
    match = re.search(r'Invoice\s*#:?\s*(\d{4,6})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Chesapeake Waste'] = {'format': 'NNNNN', 'examples': ['29149'], 'extract': _extract_chesapeake_waste_invoice}

def _extract_city_of_dumas_invoice(text: str) -> Optional[str]:
    """City of Dumas invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['City of Dumas'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_city_of_dumas_invoice}

def _extract_certified_enterprises_invoice(text: str) -> Optional[str]:
    """Certified Enterprises invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Certified Enterprises'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_certified_enterprises_invoice}

def _extract_ssw_box_services_invoice(text: str) -> Optional[str]:
    """SSW-Box Services invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['SSW-Box Services'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_ssw_box_services_invoice}

def _extract_becker_complete_invoice(text: str) -> Optional[str]:
    """Becker Complete invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Becker Complete'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_becker_complete_invoice}

def _extract_shawnee_county_solid_waste_invoice(text: str) -> Optional[str]:
    """Shawnee County Solid Waste invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Shawnee County Solid Waste'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_shawnee_county_solid_waste_invoice}

def _extract_city_of_emporia_invoice(text: str) -> Optional[str]:
    """City of Emporia invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['City of Emporia'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_city_of_emporia_invoice}

def _extract_reliable_paper_invoice(text: str) -> Optional[str]:
    """Reliable Paper invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Reliable Paper'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_reliable_paper_invoice}

def _extract_brandon_industrial_parts_invoice(text: str) -> Optional[str]:
    """Brandon Industrial Parts invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Brandon Industrial Parts'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_brandon_industrial_parts_invoice}

def _extract_skyhook_invoice(text: str) -> Optional[str]:
    """Skyhook invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Skyhook'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_skyhook_invoice}

def _extract_city_of_fort_myers_invoice(text: str) -> Optional[str]:
    """City of Fort Myers invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['City of Fort Myers'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_city_of_fort_myers_invoice}

def _extract_city_of_douglasville_invoice(text: str) -> Optional[str]:
    """City of Douglasville invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['City of Douglasville'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_city_of_douglasville_invoice}

def _extract_bower_disposal_invoice(text: str) -> Optional[str]:
    """Bower Disposal invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Bower Disposal'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_bower_disposal_invoice}

def _extract_coles_county_sanitation_invoice(text: str) -> Optional[str]:
    """Coles County Sanitation invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Coles County Sanitation'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_coles_county_sanitation_invoice}

def _extract_lance_refuse_invoice(text: str) -> Optional[str]:
    """Lance Refuse invoice extractor"""
    match = re.search(r'Invoice\s*#:?\s*(\d{4,6})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Lance Refuse'] = {'format': 'NNNNN', 'examples': ['97857'], 'extract': _extract_lance_refuse_invoice}

def _extract_kopchos_sanitation_invoice(text: str) -> Optional[str]:
    """Kopchos Sanitation invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Kopchos Sanitation'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_kopchos_sanitation_invoice}

def _extract_metech_recycling_invoice(text: str) -> Optional[str]:
    """Metech Recycling invoice extractor"""
    match = re.search(r'INV[-\s]?(\d{4,6})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Metech Recycling'] = {'format': 'INV-NNNNN', 'examples': ['85660'], 'extract': _extract_metech_recycling_invoice}

def _extract_torrez_sanitation_invoice(text: str) -> Optional[str]:
    """Torrez Sanitation invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Torrez Sanitation'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_torrez_sanitation_invoice}

def _extract_lift_waste_invoice(text: str) -> Optional[str]:
    """Lift Waste invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Lift Waste'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_lift_waste_invoice}

def _extract_vanderpoel_disposal_invoice(text: str) -> Optional[str]:
    """Vanderpoel Disposal invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Vanderpoel Disposal'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_vanderpoel_disposal_invoice}

def _extract_madden_sanitation_invoice(text: str) -> Optional[str]:
    """Madden Sanitation invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Madden Sanitation'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_madden_sanitation_invoice}

def _extract_mackenzie_disposal_invoice(text: str) -> Optional[str]:
    """Mackenzie Disposal invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Mackenzie Disposal'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_mackenzie_disposal_invoice}

def _extract_denali_disposal_invoice(text: str) -> Optional[str]:
    """Denali Disposal invoice extractor"""
    match = re.search(r'Invoice\s*#:?\s*(\d{5,7})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Denali Disposal'] = {'format': 'NNNNNN', 'examples': ['310557'], 'extract': _extract_denali_disposal_invoice}

def _extract_arg_services_invoice(text: str) -> Optional[str]:
    """Arg Services invoice extractor"""
    match = re.search(r'Invoice\s*#:?\s*(\d{4,6})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Arg Services'] = {'format': 'NNNNN', 'examples': ['34773'], 'extract': _extract_arg_services_invoice}

def _extract_byre_brothers_invoice(text: str) -> Optional[str]:
    """Byre Brothers invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Byre Brothers'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_byre_brothers_invoice}

def _extract_community_sanitation_invoice(text: str) -> Optional[str]:
    """Community Sanitation invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Community Sanitation'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_community_sanitation_invoice}

def _extract_r_r_midwest_invoice(text: str) -> Optional[str]:
    """R & R Midwest invoice extractor"""
    match = re.search(r'Invoice\s*#:?\s*(\d{6,8})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['R & R Midwest'] = {'format': 'NNNNNNN', 'examples': ['4105327'], 'extract': _extract_r_r_midwest_invoice}

def _extract_sound_disposal_inc_invoice(text: str) -> Optional[str]:
    """Sound Disposal Inc invoice extractor"""
    match = re.search(r'Invoice\s*Number:?\s*(\d{5,7})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Sound Disposal Inc'] = {'format': 'NNNNNN', 'examples': ['339691'], 'extract': _extract_sound_disposal_inc_invoice}

def _extract_cumberland_services_invoice(text: str) -> Optional[str]:
    """Cumberland Services invoice extractor"""
    match = re.search(r'Invoice\s*#:?\s*(\d{4,6})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Cumberland Services'] = {'format': 'NNNNN', 'examples': ['39221'], 'extract': _extract_cumberland_services_invoice}

def _extract_total_disposal_inc_invoice(text: str) -> Optional[str]:
    """Total Disposal Inc invoice extractor"""
    match = re.search(r'Invoice\s*No\.?:?\s*(\d{9,11})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Total Disposal Inc'] = {'format': 'NNNNNNNNNN', 'examples': ['0000632821'], 'extract': _extract_total_disposal_inc_invoice}

def _extract_hartel_s_invoice(text: str) -> Optional[str]:
    """Hartel's invoice extractor"""
    match = re.search(r'Invoice\s*Number:?\s*(\d{6,8})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Hartel\'s'] = {'format': 'NNNNNNN', 'examples': ['1239618'], 'extract': _extract_hartel_s_invoice}

def _extract_hogland_s_transfer_invoice(text: str) -> Optional[str]:
    """Hogland's Transfer invoice extractor"""
    match = re.search(r'Invoice\s*Number:?\s*(\d{6,8})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Hogland\'s Transfer'] = {'format': 'NNNNNNN', 'examples': ['5283375'], 'extract': _extract_hogland_s_transfer_invoice}

def _extract_american_eagle_waste_invoice(text: str) -> Optional[str]:
    """American Eagle Waste invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['American Eagle Waste'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_american_eagle_waste_invoice}

def _extract_area_refuse_invoice(text: str) -> Optional[str]:
    """Area Refuse invoice extractor"""
    match = re.search(r'Invoice\s*Number:?\s*(\d{5,7})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Area Refuse'] = {'format': 'NNNNNN', 'examples': ['265124'], 'extract': _extract_area_refuse_invoice}

def _extract_gogebic_range_swma_invoice(text: str) -> Optional[str]:
    """Gogebic Range SWMA invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Gogebic Range SWMA'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_gogebic_range_swma_invoice}

def _extract_kc_disposal_invoice(text: str) -> Optional[str]:
    """KC Disposal invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['KC Disposal'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_kc_disposal_invoice}

def _extract_aaa_trash_service_invoice(text: str) -> Optional[str]:
    """AAA Trash Service invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['AAA Trash Service'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_aaa_trash_service_invoice}

def _extract_greenway_waste_invoice(text: str) -> Optional[str]:
    """Greenway Waste invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Greenway Waste'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_greenway_waste_invoice}

def _extract_potties_for_the_rockies_invoice(text: str) -> Optional[str]:
    """Potties for the Rockies invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Potties for the Rockies'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_potties_for_the_rockies_invoice}

def _extract_abe_s_trash_service_invoice(text: str) -> Optional[str]:
    """Abe's Trash Service invoice extractor"""
    match = re.search(r'Invoice\s*Number:?\s*(\d{6,8})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Abe\'s Trash Service'] = {'format': 'NNNNNNN', 'examples': ['2864298'], 'extract': _extract_abe_s_trash_service_invoice}

def _extract_sonoco_recycling_invoice(text: str) -> Optional[str]:
    """Sonoco Recycling invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Sonoco Recycling'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_sonoco_recycling_invoice}

def _extract_escondido_disposal_invoice(text: str) -> Optional[str]:
    """Escondido Disposal invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Escondido Disposal'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_escondido_disposal_invoice}

def _extract_ava_s_waste_removal_invoice(text: str) -> Optional[str]:
    """Ava's Waste Removal invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Ava\'s Waste Removal'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_ava_s_waste_removal_invoice}

def _extract_lake_area_disposal_invoice(text: str) -> Optional[str]:
    """Lake Area Disposal invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Lake Area Disposal'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_lake_area_disposal_invoice}

def _extract_town_of_apple_valley_invoice(text: str) -> Optional[str]:
    """Town of Apple Valley invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Town of Apple Valley'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_town_of_apple_valley_invoice}

def _extract_bnb_disposal_invoice(text: str) -> Optional[str]:
    """BNB Disposal invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['BNB Disposal'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_bnb_disposal_invoice}

def _extract_sid_s_garbage_invoice(text: str) -> Optional[str]:
    """Sid's Garbage invoice extractor"""
    match = re.search(r'Invoice\s*No\.?:?\s*(\d{4,6})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Sid\'s Garbage'] = {'format': 'NNNNN', 'examples': ['26870'], 'extract': _extract_sid_s_garbage_invoice}

def _extract_long_beach_container_invoice(text: str) -> Optional[str]:
    """Long Beach Container invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Long Beach Container'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_long_beach_container_invoice}

def _extract_aztec_waste_invoice(text: str) -> Optional[str]:
    """Aztec Waste invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Aztec Waste'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_aztec_waste_invoice}

def _extract_mountain_disposal_inc_invoice(text: str) -> Optional[str]:
    """Mountain Disposal Inc invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Mountain Disposal Inc'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_mountain_disposal_inc_invoice}

def _extract_reno_forklift_invoice(text: str) -> Optional[str]:
    """Reno Forklift invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Reno Forklift'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_reno_forklift_invoice}

def _extract_ramona_disposal_invoice(text: str) -> Optional[str]:
    """Ramona Disposal invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Ramona Disposal'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_ramona_disposal_invoice}

def _extract_dc_waste_invoice(text: str) -> Optional[str]:
    """DC Waste invoice extractor"""
    match = re.search(r'Invoice\s*Number:?\s*(\d{6,8})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['DC Waste'] = {'format': 'NNNNNNN', 'examples': ['3744800'], 'extract': _extract_dc_waste_invoice}

def _extract_filco_invoice(text: str) -> Optional[str]:
    """Filco invoice extractor"""
    match = re.search(r'Invoice\s*#:?\s*(\d{5,7})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Filco'] = {'format': 'NNNNNN', 'examples': ['415550'], 'extract': _extract_filco_invoice}

def _extract_roosevelt_ut_invoice(text: str) -> Optional[str]:
    """Roosevelt UT invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Roosevelt UT'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_roosevelt_ut_invoice}

def _extract_pyles_demolition_recycling_invoice(text: str) -> Optional[str]:
    """Pyles Demolition Recycling invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Pyles Demolition Recycling'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_pyles_demolition_recycling_invoice}

def _extract_willey_disposal_invoice(text: str) -> Optional[str]:
    """Willey Disposal invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Willey Disposal'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_willey_disposal_invoice}

def _extract_shular_s_trash_service_invoice(text: str) -> Optional[str]:
    """Shular's Trash Service invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Shular\'s Trash Service'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_shular_s_trash_service_invoice}

def _extract_nooksack_valley_disposal_invoice(text: str) -> Optional[str]:
    """Nooksack Valley Disposal invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Nooksack Valley Disposal'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_nooksack_valley_disposal_invoice}

def _extract_sanitary_service_company_invoice(text: str) -> Optional[str]:
    """Sanitary Service Company invoice extractor"""
    match = re.search(r'Invoice\s*#:?\s*(\d{7,9})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Sanitary Service Company'] = {'format': 'NNNNNNNN', 'examples': ['24989589'], 'extract': _extract_sanitary_service_company_invoice}

def _extract_family_trash_service_invoice(text: str) -> Optional[str]:
    """Family Trash Service invoice extractor"""
    match = re.search(r'Invoice\s*#:?\s*(\d{4,6})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Family Trash Service'] = {'format': 'NNNNN', 'examples': ['59938'], 'extract': _extract_family_trash_service_invoice}

def _extract_mike_spano_sons_invoice(text: str) -> Optional[str]:
    """Mike Spano & Sons invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Mike Spano & Sons'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_mike_spano_sons_invoice}

def _extract_mcgree_trucking_invoice(text: str) -> Optional[str]:
    """McGree Trucking invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['McGree Trucking'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_mcgree_trucking_invoice}

def _extract_cheyenne_board_of_public_utilities_invoice(text: str) -> Optional[str]:
    """Cheyenne Board of Public Utilities invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Cheyenne Board of Public Utilities'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_cheyenne_board_of_public_utilities_invoice}

def _extract_hiltz_invoice(text: str) -> Optional[str]:
    """Hiltz invoice extractor"""
    match = re.search(r'Invoice\s*No\.?:?\s*(\d{9,11})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Hiltz'] = {'format': 'NNNNNNNNNN', 'examples': ['0000188306'], 'extract': _extract_hiltz_invoice}

def _extract_panola_county_solid_waste_invoice(text: str) -> Optional[str]:
    """Panola County Solid Waste invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Panola County Solid Waste'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_panola_county_solid_waste_invoice}

def _extract_redwood_waste_invoice(text: str) -> Optional[str]:
    """Redwood Waste invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Redwood Waste'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_redwood_waste_invoice}

def _extract_island_refuse_invoice(text: str) -> Optional[str]:
    """Island Refuse invoice extractor"""
    match = re.search(r'Invoice\s*#:?\s*(\d{4,6})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Island Refuse'] = {'format': 'NNNNN', 'examples': ['19829'], 'extract': _extract_island_refuse_invoice}

def _extract_joseph_j_runner_invoice(text: str) -> Optional[str]:
    """Joseph J. Runner invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Joseph J. Runner'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_joseph_j_runner_invoice}

def _extract_city_of_willcox_invoice(text: str) -> Optional[str]:
    """City of Willcox invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['City of Willcox'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_city_of_willcox_invoice}

def _extract_bozzuto_brs_services_invoice(text: str) -> Optional[str]:
    """Bozzuto BRS Services invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Bozzuto BRS Services'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_bozzuto_brs_services_invoice}

def _extract_serious_sanitation_invoice(text: str) -> Optional[str]:
    """Serious Sanitation invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Serious Sanitation'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_serious_sanitation_invoice}

def _extract_ingrum_waste_disposal_invoice(text: str) -> Optional[str]:
    """Ingrum Waste Disposal invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Ingrum Waste Disposal'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_ingrum_waste_disposal_invoice}

def _extract_city_of_winters_invoice(text: str) -> Optional[str]:
    """City of Winters invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['City of Winters'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_city_of_winters_invoice}

def _extract_golden_triangle_waste_invoice(text: str) -> Optional[str]:
    """Golden Triangle Waste invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Golden Triangle Waste'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_golden_triangle_waste_invoice}

def _extract_anchor_technical_invoice(text: str) -> Optional[str]:
    """Anchor Technical invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Anchor Technical'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_anchor_technical_invoice}

def _extract_clark_s_disposal_invoice(text: str) -> Optional[str]:
    """Clark's Disposal invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Clark\'s Disposal'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_clark_s_disposal_invoice}

def _extract_tri_state_disposal_invoice(text: str) -> Optional[str]:
    """Tri-State Disposal invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Tri-State Disposal'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_tri_state_disposal_invoice}

def _extract_missoula_compost_invoice(text: str) -> Optional[str]:
    """Missoula Compost invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Missoula Compost'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_missoula_compost_invoice}

def _extract_checksammy_invoice(text: str) -> Optional[str]:
    """Checksammy invoice extractor"""
    match = re.search(r'Invoice\s*#:?\s*(\d{5,7})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Checksammy'] = {'format': 'NNNNNN', 'examples': ['174634'], 'extract': _extract_checksammy_invoice}

def _extract_busy_bee_disposal_invoice(text: str) -> Optional[str]:
    """Busy Bee Disposal invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Busy Bee Disposal'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_busy_bee_disposal_invoice}

def _extract_recycling_center_of_north_dakota_invoice(text: str) -> Optional[str]:
    """Recycling Center of North Dakota invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Recycling Center of North Dakota'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_recycling_center_of_north_dakota_invoice}

def _extract_r_s_waste_invoice(text: str) -> Optional[str]:
    """R&S Waste invoice extractor"""
    match = re.search(r'Invoice\s*#:?\s*(\d{6,8})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['R&S Waste'] = {'format': 'NNNNNNN', 'examples': ['2119733'], 'extract': _extract_r_s_waste_invoice}

def _extract_pullman_disposal_invoice(text: str) -> Optional[str]:
    """Pullman Disposal invoice extractor"""
    match = re.search(r'INV[-\s]?(\d{4,6})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Pullman Disposal'] = {'format': 'INV-NNNNN', 'examples': ['13392'], 'extract': _extract_pullman_disposal_invoice}

def _extract_watertown_iron_invoice(text: str) -> Optional[str]:
    """Watertown Iron invoice extractor"""
    match = re.search(r'Invoice\s*#:?\s*(\d{4,6})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Watertown Iron'] = {'format': 'NNNNN', 'examples': ['23693'], 'extract': _extract_watertown_iron_invoice}

def _extract_accurate_paper_recycling_invoice(text: str) -> Optional[str]:
    """Accurate Paper Recycling invoice extractor"""
    match = re.search(r'Invoice\s*No\.?:?\s*(\d{4,6})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Accurate Paper Recycling'] = {'format': 'NNNNN', 'examples': ['69322'], 'extract': _extract_accurate_paper_recycling_invoice}

def _extract_gear_for_waste_invoice(text: str) -> Optional[str]:
    """Gear For Waste invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Gear For Waste'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_gear_for_waste_invoice}

def _extract_wampler_services_invoice(text: str) -> Optional[str]:
    """Wampler Services invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Wampler Services'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_wampler_services_invoice}

def _extract_junk_king_invoice(text: str) -> Optional[str]:
    """Junk King invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Junk King'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_junk_king_invoice}

def _extract_westport_funding_invoice(text: str) -> Optional[str]:
    """Westport Funding invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Westport Funding'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_westport_funding_invoice}

def _extract_city_of_quincy_invoice(text: str) -> Optional[str]:
    """City of Quincy invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['City of Quincy'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_city_of_quincy_invoice}

def _extract_top_dog_waste_invoice(text: str) -> Optional[str]:
    """Top Dog Waste invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Top Dog Waste'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_top_dog_waste_invoice}

def _extract_solomon_container_service_invoice(text: str) -> Optional[str]:
    """Solomon Container Service invoice extractor"""
    match = re.search(r'Invoice\s*#:?\s*(\d{5,7})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Solomon Container Service'] = {'format': 'NNNNNN', 'examples': ['222691'], 'extract': _extract_solomon_container_service_invoice}

def _extract_tom_danley_disposal_invoice(text: str) -> Optional[str]:
    """Tom Danley Disposal invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Tom Danley Disposal'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_tom_danley_disposal_invoice}

def _extract_garretson_trash_service_invoice(text: str) -> Optional[str]:
    """Garretson Trash Service invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Garretson Trash Service'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_garretson_trash_service_invoice}

def _extract_dayne_s_waste_disposal_invoice(text: str) -> Optional[str]:
    """Dayne's Waste Disposal invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Dayne\'s Waste Disposal'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_dayne_s_waste_disposal_invoice}

def _extract_triple_h_enterprises_invoice(text: str) -> Optional[str]:
    """Triple H Enterprises invoice extractor"""
    match = re.search(r'Inv\s*#:?\s*(\d{5,7})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Triple H Enterprises'] = {'format': 'NNNNNN', 'examples': ['163416'], 'extract': _extract_triple_h_enterprises_invoice}

def _extract_wb_waste_solutions_invoice(text: str) -> Optional[str]:
    """WB Waste Solutions invoice extractor"""
    match = re.search(r'Invoice\s*No\.?:?\s*(\d{9,11})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['WB Waste Solutions'] = {'format': 'NNNNNNNNNN', 'examples': ['1301395149'], 'extract': _extract_wb_waste_solutions_invoice}

def _extract_waste_disposal_az_invoice(text: str) -> Optional[str]:
    """Waste Disposal AZ invoice extractor"""
    match = re.search(r'Invoice\s*Number:?\s*(\d{5,7})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Waste Disposal AZ'] = {'format': 'NNNNNN', 'examples': ['322107'], 'extract': _extract_waste_disposal_az_invoice}

def _extract_kirby_sanitation_invoice(text: str) -> Optional[str]:
    """Kirby Sanitation invoice extractor"""
    match = re.search(r'Invoice\s*No\.?:?\s*(\d{9,11})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Kirby Sanitation'] = {'format': 'NNNNNNNNNN', 'examples': ['0001403442'], 'extract': _extract_kirby_sanitation_invoice}

def _extract_winston_sanitary_invoice(text: str) -> Optional[str]:
    """Winston Sanitary invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Winston Sanitary'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_winston_sanitary_invoice}

def _extract_copper_state_sanitation_invoice(text: str) -> Optional[str]:
    """Copper State Sanitation invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Copper State Sanitation'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_copper_state_sanitation_invoice}

def _extract_north_georgia_waste_invoice(text: str) -> Optional[str]:
    """North Georgia Waste invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['North Georgia Waste'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_north_georgia_waste_invoice}

def _extract_pratt_recycling_invoice(text: str) -> Optional[str]:
    """Pratt Recycling invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Pratt Recycling'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_pratt_recycling_invoice}

def _extract_gil_s_sanitation_invoice(text: str) -> Optional[str]:
    """Gil's Sanitation invoice extractor"""
    match = re.search(r'Invoice\s*#:?\s*(\d{5,7})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Gil\'s Sanitation'] = {'format': 'NNNNNN', 'examples': ['136826'], 'extract': _extract_gil_s_sanitation_invoice}

def _extract_buckingham_companies_invoice(text: str) -> Optional[str]:
    """Buckingham Companies invoice extractor"""
    match = re.search(r'Invoice\s*#:?\s*(\d{5,7})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Buckingham Companies'] = {'format': 'NNNNNN', 'examples': ['525822'], 'extract': _extract_buckingham_companies_invoice}

def _extract_top_of_the_line_dumpsters_invoice(text: str) -> Optional[str]:
    """Top of the Line Dumpsters invoice extractor"""
    match = re.search(r'INV[-\s]?(\d{4,6})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Top of the Line Dumpsters'] = {'format': 'INV-NNNNN', 'examples': ['47019'], 'extract': _extract_top_of_the_line_dumpsters_invoice}

def _extract_all_state_waste_inc_invoice(text: str) -> Optional[str]:
    """All State Waste Inc invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['All State Waste Inc'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_all_state_waste_inc_invoice}

def _extract_armor_environmental_invoice(text: str) -> Optional[str]:
    """Armor Environmental invoice extractor"""
    match = re.search(r'Invoice\s*#:?\s*(\d{4,6})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Armor Environmental'] = {'format': 'NNNNN', 'examples': ['20316'], 'extract': _extract_armor_environmental_invoice}

def _extract_city_of_nampa_invoice(text: str) -> Optional[str]:
    """City of Nampa invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['City of Nampa'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_city_of_nampa_invoice}

def _extract_chisago_lakes_sanitation_invoice(text: str) -> Optional[str]:
    """Chisago Lakes Sanitation invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Chisago Lakes Sanitation'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_chisago_lakes_sanitation_invoice}

def _extract_nevada_recycling_invoice(text: str) -> Optional[str]:
    """Nevada Recycling invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Nevada Recycling'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_nevada_recycling_invoice}

def _extract_dedicated_dumpster_service_invoice(text: str) -> Optional[str]:
    """Dedicated Dumpster Service invoice extractor"""
    match = re.search(r'Invoice\s*#:?\s*(\d{4,6})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Dedicated Dumpster Service'] = {'format': 'NNNNN', 'examples': ['51888'], 'extract': _extract_dedicated_dumpster_service_invoice}

def _extract_glendale_arizona_utilities_invoice(text: str) -> Optional[str]:
    """Glendale Arizona Utilities invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Glendale Arizona Utilities'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_glendale_arizona_utilities_invoice}

def _extract_impact_environmental_invoice(text: str) -> Optional[str]:
    """Impact Environmental invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Impact Environmental'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_impact_environmental_invoice}

def _extract_city_of_baxley_invoice(text: str) -> Optional[str]:
    """City of Baxley invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['City of Baxley'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_city_of_baxley_invoice}

def _extract_citrus_county_utilities_invoice(text: str) -> Optional[str]:
    """Citrus County Utilities invoice extractor"""
    match = re.search(r'Invoice\s*Number:?\s*(\d{9,11})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Citrus County Utilities'] = {'format': 'NNNNNNNNNN', 'examples': ['0002476044'], 'extract': _extract_citrus_county_utilities_invoice}

def _extract_salt_river_pima_invoice(text: str) -> Optional[str]:
    """Salt River Pima invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Salt River Pima'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_salt_river_pima_invoice}

def _extract_bloom_waste_invoice(text: str) -> Optional[str]:
    """Bloom Waste invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Bloom Waste'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_bloom_waste_invoice}

def _extract_windsor_sanitation_invoice(text: str) -> Optional[str]:
    """Windsor Sanitation invoice extractor"""
    match = re.search(r'Invoice\s*No\.?:?\s*(\d{9,11})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Windsor Sanitation'] = {'format': 'NNNNNNNNNN', 'examples': ['0000398782'], 'extract': _extract_windsor_sanitation_invoice}

def _extract_ez_disposal_invoice(text: str) -> Optional[str]:
    """EZ Disposal invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['EZ Disposal'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_ez_disposal_invoice}

def _extract_rockwood_sustainable_solutions_invoice(text: str) -> Optional[str]:
    """Rockwood Sustainable Solutions invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Rockwood Sustainable Solutions'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_rockwood_sustainable_solutions_invoice}

def _extract_al_clawson_disposal_invoice(text: str) -> Optional[str]:
    """Al Clawson Disposal invoice extractor"""
    match = re.search(r'Invoice\s*#:?\s*(\d{5,7})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Al Clawson Disposal'] = {'format': 'NNNNNN', 'examples': ['758080'], 'extract': _extract_al_clawson_disposal_invoice}

def _extract_city_of_vinita_invoice(text: str) -> Optional[str]:
    """City of Vinita invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['City of Vinita'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_city_of_vinita_invoice}

def _extract_anchorage_solid_waste_invoice(text: str) -> Optional[str]:
    """Anchorage Solid Waste invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Anchorage Solid Waste'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_anchorage_solid_waste_invoice}

def _extract_pendleton_sanitary_service_invoice(text: str) -> Optional[str]:
    """Pendleton Sanitary Service invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Pendleton Sanitary Service'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_pendleton_sanitary_service_invoice}

def _extract_hbs_denver_invoice(text: str) -> Optional[str]:
    """HBS Denver invoice extractor"""
    match = re.search(r'Invoice\s*#?:?\s*([A-Z]{1,3}[-]?\d{6,9})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['HBS Denver'] = {'format': 'XX-NNNNNN', 'examples': ['FR5451385'], 'extract': _extract_hbs_denver_invoice}

def _extract_tim_s_trash_service_invoice(text: str) -> Optional[str]:
    """Tim's Trash Service invoice extractor"""
    match = re.search(r'INV[-\s]?(\d{3,5})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Tim\'s Trash Service'] = {'format': 'INV-NNNN', 'examples': ['4375'], 'extract': _extract_tim_s_trash_service_invoice}

def _extract_horn_sanitation_invoice(text: str) -> Optional[str]:
    """Horn Sanitation invoice extractor"""
    match = re.search(r'Invoice\s*#:?\s*(\d{4,6})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Horn Sanitation'] = {'format': 'NNNNN', 'examples': ['10130'], 'extract': _extract_horn_sanitation_invoice}

def _extract_united_waste_systems_invoice(text: str) -> Optional[str]:
    """United Waste Systems invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['United Waste Systems'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_united_waste_systems_invoice}

def _extract_toro_waste_invoice(text: str) -> Optional[str]:
    """Toro Waste invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Toro Waste'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_toro_waste_invoice}

def _extract_kurtzman_s_sanitation_invoice(text: str) -> Optional[str]:
    """Kurtzman's Sanitation invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Kurtzman\'s Sanitation'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_kurtzman_s_sanitation_invoice}

def _extract_southern_illinois_waste_invoice(text: str) -> Optional[str]:
    """Southern Illinois Waste invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Southern Illinois Waste'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_southern_illinois_waste_invoice}

def _extract_central_valley_disposal_invoice(text: str) -> Optional[str]:
    """Central Valley Disposal invoice extractor"""
    match = re.search(r'Invoice\s*#:?\s*(\d{7,9})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Central Valley Disposal'] = {'format': 'NNNNNNNN', 'examples': ['05202538'], 'extract': _extract_central_valley_disposal_invoice}

def _extract_cogent_waste_solutions_invoice(text: str) -> Optional[str]:
    """Cogent Waste Solutions invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Cogent Waste Solutions'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_cogent_waste_solutions_invoice}

def _extract_gtx_gainsborough_waste_invoice(text: str) -> Optional[str]:
    """GTX Gainsborough Waste invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['GTX Gainsborough Waste'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_gtx_gainsborough_waste_invoice}

def _extract_opdenaker_trash_invoice(text: str) -> Optional[str]:
    """Opdenaker Trash invoice extractor"""
    match = re.search(r'Invoice\s*#:?\s*(\d{5,7})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Opdenaker Trash'] = {'format': 'NNNNNN', 'examples': ['806671'], 'extract': _extract_opdenaker_trash_invoice}

def _extract_all_florida_scrap_metals_invoice(text: str) -> Optional[str]:
    """All Florida Scrap Metals invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['All Florida Scrap Metals'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_all_florida_scrap_metals_invoice}

def _extract_patterson_sanitation_invoice(text: str) -> Optional[str]:
    """Patterson Sanitation invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Patterson Sanitation'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_patterson_sanitation_invoice}

def _extract_waste_disposal_services_invoice(text: str) -> Optional[str]:
    """Waste Disposal Services invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Waste Disposal Services'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_waste_disposal_services_invoice}

def _extract_control_waste_invoice(text: str) -> Optional[str]:
    """Control Waste invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Control Waste'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_control_waste_invoice}

def _extract_mulberry_ventures_invoice(text: str) -> Optional[str]:
    """Mulberry Ventures invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Mulberry Ventures'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_mulberry_ventures_invoice}

def _extract_sutter_disposal_invoice(text: str) -> Optional[str]:
    """Sutter Disposal invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Sutter Disposal'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_sutter_disposal_invoice}

def _extract_town_of_gardnerville_invoice(text: str) -> Optional[str]:
    """Town of Gardnerville invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Town of Gardnerville'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_town_of_gardnerville_invoice}

def _extract_clackamas_garbage_invoice(text: str) -> Optional[str]:
    """Clackamas Garbage invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Clackamas Garbage'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_clackamas_garbage_invoice}

def _extract_get_rid_of_it_waste_invoice(text: str) -> Optional[str]:
    """Get Rid Of It Waste invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Get Rid Of It Waste'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_get_rid_of_it_waste_invoice}

def _extract_myers_container_service_invoice(text: str) -> Optional[str]:
    """Myers Container Service invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Myers Container Service'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_myers_container_service_invoice}

def _extract_green_environmental_services_invoice(text: str) -> Optional[str]:
    """Green Environmental Services invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Green Environmental Services'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_green_environmental_services_invoice}

def _extract_humpty_dumpsters_invoice(text: str) -> Optional[str]:
    """Humpty Dumpsters invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Humpty Dumpsters'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_humpty_dumpsters_invoice}

def _extract_keys_sanitary_invoice(text: str) -> Optional[str]:
    """Keys Sanitary invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Keys Sanitary'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_keys_sanitary_invoice}

def _extract_step_up_disposals_invoice(text: str) -> Optional[str]:
    """Step Up Disposals invoice extractor"""
    match = re.search(r'Invoice\s*No\.?:?\s*(\d{4,6})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Step Up Disposals'] = {'format': 'NNNNN', 'examples': ['39149'], 'extract': _extract_step_up_disposals_invoice}

def _extract_enevo_invoice(text: str) -> Optional[str]:
    """Enevo invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Enevo'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_enevo_invoice}

def _extract_hillside_solutions_invoice(text: str) -> Optional[str]:
    """Hillside Solutions invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Hillside Solutions'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_hillside_solutions_invoice}

def _extract_city_of_madisonville_invoice(text: str) -> Optional[str]:
    """City of Madisonville invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['City of Madisonville'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_city_of_madisonville_invoice}

def _extract_federal_recycling_waste_solutions_invoice(text: str) -> Optional[str]:
    """Federal Recycling & Waste Solutions invoice extractor"""
    match = re.search(r'Invoice\s*No\.?:?\s*(\d{6,8})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Federal Recycling & Waste Solutions'] = {'format': 'NNNNNNN', 'examples': ['1381478'], 'extract': _extract_federal_recycling_waste_solutions_invoice}

def _extract_tri_county_disposal_invoice(text: str) -> Optional[str]:
    """Tri County Disposal invoice extractor"""
    match = re.search(r'Invoice\s*Number:?\s*(\d{5,7})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Tri County Disposal'] = {'format': 'NNNNNN', 'examples': ['222555'], 'extract': _extract_tri_county_disposal_invoice}

def _extract_self_recycling_invoice(text: str) -> Optional[str]:
    """Self Recycling invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Self Recycling'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_self_recycling_invoice}

def _extract_delta_garbage_service_invoice(text: str) -> Optional[str]:
    """Delta Garbage Service invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Delta Garbage Service'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_delta_garbage_service_invoice}

def _extract_north_port_solid_waste_invoice(text: str) -> Optional[str]:
    """North Port Solid Waste invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['North Port Solid Waste'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_north_port_solid_waste_invoice}

def _extract_mt_diablo_resource_recovery_invoice(text: str) -> Optional[str]:
    """Mt Diablo Resource Recovery invoice extractor"""
    match = re.search(r'Invoice\s*#:?\s*(\d{6,8})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Mt Diablo Resource Recovery'] = {'format': 'NNNNNNN', 'examples': ['2579027'], 'extract': _extract_mt_diablo_resource_recovery_invoice}

def _extract_larry_d_marshall_disposal_invoice(text: str) -> Optional[str]:
    """Larry D Marshall Disposal invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Larry D Marshall Disposal'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_larry_d_marshall_disposal_invoice}

def _extract_north_iredell_sanitation_invoice(text: str) -> Optional[str]:
    """North Iredell Sanitation invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['North Iredell Sanitation'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_north_iredell_sanitation_invoice}

def _extract_old_west_disposal_invoice(text: str) -> Optional[str]:
    """Old West Disposal invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Old West Disposal'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_old_west_disposal_invoice}

def _extract_recycling_center_inc_invoice(text: str) -> Optional[str]:
    """Recycling Center Inc invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Recycling Center Inc'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_recycling_center_inc_invoice}

def _extract_bozeman_mt_utilities_invoice(text: str) -> Optional[str]:
    """Bozeman MT Utilities invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Bozeman MT Utilities'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_bozeman_mt_utilities_invoice}

def _extract_city_of_craig_invoice(text: str) -> Optional[str]:
    """City of Craig invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['City of Craig'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_city_of_craig_invoice}

def _extract_roseburg_disposal_invoice(text: str) -> Optional[str]:
    """Roseburg Disposal invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Roseburg Disposal'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_roseburg_disposal_invoice}

def _extract_city_of_colby_invoice(text: str) -> Optional[str]:
    """City of Colby invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['City of Colby'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_city_of_colby_invoice}

def _extract_prolex_compacting_invoice(text: str) -> Optional[str]:
    """Prolex Compacting invoice extractor"""
    match = re.search(r'Invoice\s*#:?\s*(\d{4,6})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Prolex Compacting'] = {'format': 'NNNNN', 'examples': ['13009'], 'extract': _extract_prolex_compacting_invoice}

def _extract_expert_transportation_invoice(text: str) -> Optional[str]:
    """Expert Transportation invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Expert Transportation'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_expert_transportation_invoice}

def _extract_waste_removal_recycling_invoice(text: str) -> Optional[str]:
    """Waste Removal & Recycling invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Waste Removal & Recycling'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_waste_removal_recycling_invoice}

def _extract_mavilyn_industries_invoice(text: str) -> Optional[str]:
    """Mavilyn Industries invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Mavilyn Industries'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_mavilyn_industries_invoice}

def _extract_j_s_trash_collection_invoice(text: str) -> Optional[str]:
    """J & S Trash Collection invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['J & S Trash Collection'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_j_s_trash_collection_invoice}

def _extract_westside_disposal_invoice(text: str) -> Optional[str]:
    """Westside Disposal invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Westside Disposal'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_westside_disposal_invoice}

def _extract_4g_futures_invoice(text: str) -> Optional[str]:
    """4G Futures invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['4G Futures'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_4g_futures_invoice}

def _extract_nva_services_invoice(text: str) -> Optional[str]:
    """NVA Services invoice extractor"""
    match = re.search(r'Invoice\s*Number:?\s*(\d{6,8})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['NVA Services'] = {'format': 'NNNNNNN', 'examples': ['1230849'], 'extract': _extract_nva_services_invoice}

def _extract_omni_invoice(text: str) -> Optional[str]:
    """Omni invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Omni'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_omni_invoice}

def _extract_city_of_dickinson_invoice(text: str) -> Optional[str]:
    """City of Dickinson invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['City of Dickinson'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_city_of_dickinson_invoice}

def _extract_palm_springs_disposal_invoice(text: str) -> Optional[str]:
    """Palm Springs Disposal invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Palm Springs Disposal'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_palm_springs_disposal_invoice}

def _extract_tacoma_public_utilities_invoice(text: str) -> Optional[str]:
    """Tacoma Public Utilities invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Tacoma Public Utilities'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_tacoma_public_utilities_invoice}

def _extract_graybill_equipment_repair_invoice(text: str) -> Optional[str]:
    """Graybill Equipment & Repair invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Graybill Equipment & Repair'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_graybill_equipment_repair_invoice}

def _extract_commonwealth_waste_solutions_invoice(text: str) -> Optional[str]:
    """Commonwealth Waste Solutions invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Commonwealth Waste Solutions'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_commonwealth_waste_solutions_invoice}

def _extract_snake_river_dispose_all_invoice(text: str) -> Optional[str]:
    """Snake River Dispose-All invoice extractor"""
    match = re.search(r'Inv\s*#:?\s*(\d{6,8})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Snake River Dispose-All'] = {'format': 'NNNNNNN', 'examples': ['6049261'], 'extract': _extract_snake_river_dispose_all_invoice}

def _extract_south_plains_waste_invoice(text: str) -> Optional[str]:
    """South Plains Waste invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['South Plains Waste'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_south_plains_waste_invoice}

def _extract_canusa_hershman_invoice(text: str) -> Optional[str]:
    """Canusa Hershman invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Canusa Hershman'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_canusa_hershman_invoice}

def _extract_forever_clean_invoice(text: str) -> Optional[str]:
    """Forever Clean invoice extractor"""
    match = re.search(r'Invoice\s*#?:?\s*([A-Z]{1,3}[-]?\d{4,7})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Forever Clean'] = {'format': 'XX-NNNN', 'examples': ['I100101'], 'extract': _extract_forever_clean_invoice}

def _extract_durflinger_disposal_service_invoice(text: str) -> Optional[str]:
    """Durflinger Disposal Service invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Durflinger Disposal Service'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_durflinger_disposal_service_invoice}

def _extract_reliable_paper_recycling_invoice(text: str) -> Optional[str]:
    """Reliable Paper Recycling invoice extractor"""
    match = re.search(r'Invoice\s*#:?\s*(\d{4,6})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Reliable Paper Recycling'] = {'format': 'NNNNN', 'examples': ['89849'], 'extract': _extract_reliable_paper_recycling_invoice}

def _extract_aspen_leasing_invoice(text: str) -> Optional[str]:
    """Aspen Leasing invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Aspen Leasing'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_aspen_leasing_invoice}

def _extract_darling_ingredients_invoice(text: str) -> Optional[str]:
    """Darling Ingredients invoice extractor"""
    match = re.search(r'Invoice\s*Number:?\s*(\d{7,9})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Darling Ingredients'] = {'format': 'NNNNNNNN', 'examples': ['14211077'], 'extract': _extract_darling_ingredients_invoice}

def _extract_city_of_laramie_invoice(text: str) -> Optional[str]:
    """City of Laramie invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['City of Laramie'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_city_of_laramie_invoice}

def _extract_jamaica_ash_rubbish_invoice(text: str) -> Optional[str]:
    """Jamaica Ash & Rubbish invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Jamaica Ash & Rubbish'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_jamaica_ash_rubbish_invoice}

def _extract_kings_roll_off_invoice(text: str) -> Optional[str]:
    """Kings Roll-Off invoice extractor"""
    match = re.search(r'Invoice\s*No\.?:?\s*(\d{4,6})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Kings Roll-Off'] = {'format': 'NNNNN', 'examples': ['16735'], 'extract': _extract_kings_roll_off_invoice}

def _extract_capital_city_invoice(text: str) -> Optional[str]:
    """Capital City invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Capital City'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_capital_city_invoice}

def _extract_city_of_rolla_invoice(text: str) -> Optional[str]:
    """City of Rolla invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['City of Rolla'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_city_of_rolla_invoice}

def _extract_city_of_williston_invoice(text: str) -> Optional[str]:
    """City of Williston invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['City of Williston'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_city_of_williston_invoice}

def _extract_earthsavers_invoice(text: str) -> Optional[str]:
    """EarthSavers invoice extractor"""
    match = re.search(r'Invoice\s*Number:?\s*(\d{4,6})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['EarthSavers'] = {'format': 'NNNNN', 'examples': ['41717'], 'extract': _extract_earthsavers_invoice}

def _extract_dallas_recycling_invoice(text: str) -> Optional[str]:
    """Dallas Recycling invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Dallas Recycling'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_dallas_recycling_invoice}

def _extract_murray_sanitation_invoice(text: str) -> Optional[str]:
    """Murray Sanitation invoice extractor"""
    match = re.search(r'Invoice\s*No\.?:?\s*(\d{6,8})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Murray Sanitation'] = {'format': 'NNNNNNN', 'examples': ['5017154'], 'extract': _extract_murray_sanitation_invoice}

def _extract_nicholas_sanitation_invoice(text: str) -> Optional[str]:
    """Nicholas Sanitation invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Nicholas Sanitation'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_nicholas_sanitation_invoice}

def _extract_absolute_services_invoice(text: str) -> Optional[str]:
    """Absolute Services invoice extractor"""
    match = re.search(r'Invoice\s*#:?\s*(\d{4,6})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Absolute Services'] = {'format': 'NNNNN', 'examples': ['15226'], 'extract': _extract_absolute_services_invoice}

def _extract_ab_8_waste_solutions_invoice(text: str) -> Optional[str]:
    """AB-8 Waste Solutions invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['AB-8 Waste Solutions'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_ab_8_waste_solutions_invoice}

def _extract_brannon_industrial_invoice(text: str) -> Optional[str]:
    """Brannon Industrial invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Brannon Industrial'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_brannon_industrial_invoice}

def _extract_perdue_environmental_invoice(text: str) -> Optional[str]:
    """Perdue Environmental invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Perdue Environmental'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_perdue_environmental_invoice}

def _extract_cwsi_invoice(text: str) -> Optional[str]:
    """CWSI invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['CWSI'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_cwsi_invoice}

def _extract_maui_disposal_co_invoice(text: str) -> Optional[str]:
    """Maui Disposal Co invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Maui Disposal Co'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_maui_disposal_co_invoice}

def _extract_edge_waste_invoice(text: str) -> Optional[str]:
    """Edge Waste invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Edge Waste'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_edge_waste_invoice}

def _extract_wasteless_solutions_invoice(text: str) -> Optional[str]:
    """Wasteless Solutions invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Wasteless Solutions'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_wasteless_solutions_invoice}

def _extract_h_h_sanitation_invoice(text: str) -> Optional[str]:
    """H & H Sanitation invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['H & H Sanitation'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_h_h_sanitation_invoice}

def _extract_hometown_disposal_invoice(text: str) -> Optional[str]:
    """Hometown Disposal invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Hometown Disposal'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_hometown_disposal_invoice}

def _extract_centre_water_works_invoice(text: str) -> Optional[str]:
    """Centre Water Works invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Centre Water Works'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_centre_water_works_invoice}

def _extract_mid_ohio_sanitation_recycling_invoice(text: str) -> Optional[str]:
    """Mid-Ohio Sanitation & Recycling invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Mid-Ohio Sanitation & Recycling'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_mid_ohio_sanitation_recycling_invoice}

def _extract_smoky_mountain_waste_invoice(text: str) -> Optional[str]:
    """Smoky Mountain Waste invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Smoky Mountain Waste'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_smoky_mountain_waste_invoice}

def _extract_scraps_compost_invoice(text: str) -> Optional[str]:
    """Scraps Compost invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Scraps Compost'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_scraps_compost_invoice}

def _extract_jim_dedman_s_sanitation_invoice(text: str) -> Optional[str]:
    """Jim Dedman's Sanitation invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Jim Dedman\'s Sanitation'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_jim_dedman_s_sanitation_invoice}

def _extract_nisly_brothers_invoice(text: str) -> Optional[str]:
    """Nisly Brothers invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Nisly Brothers'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_nisly_brothers_invoice}

def _extract_a_l_compaction_invoice(text: str) -> Optional[str]:
    """A&L Compaction invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['A&L Compaction'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_a_l_compaction_invoice}

def _extract_j_r_sanitation_invoice(text: str) -> Optional[str]:
    """J&R Sanitation invoice extractor"""
    match = re.search(r'Invoice\s*#:?\s*(\d{4,6})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['J&R Sanitation'] = {'format': 'NNNNN', 'examples': ['25503'], 'extract': _extract_j_r_sanitation_invoice}

def _extract_california_waste_recovery_invoice(text: str) -> Optional[str]:
    """California Waste Recovery invoice extractor"""
    match = re.search(r'Invoice\s*#:?\s*(\d{5,7})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['California Waste Recovery'] = {'format': 'NNNNNN', 'examples': ['838816'], 'extract': _extract_california_waste_recovery_invoice}

def _extract_niese_hauling_invoice(text: str) -> Optional[str]:
    """Niese Hauling invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Niese Hauling'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_niese_hauling_invoice}

def _extract_tahoe_basin_container_invoice(text: str) -> Optional[str]:
    """Tahoe Basin Container invoice extractor"""
    match = re.search(r'Invoice\s*#:?\s*(\d{5,7})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Tahoe Basin Container'] = {'format': 'NNNNNN', 'examples': ['287189'], 'extract': _extract_tahoe_basin_container_invoice}

def _extract_key_disposal_recycling_invoice(text: str) -> Optional[str]:
    """Key Disposal & Recycling invoice extractor"""
    match = re.search(r'Invoice\s*#:?\s*(\d{7,9})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Key Disposal & Recycling'] = {'format': 'NNNNNNNN', 'examples': ['59100037'], 'extract': _extract_key_disposal_recycling_invoice}

def _extract_delta_disposal_invoice(text: str) -> Optional[str]:
    """Delta Disposal invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Delta Disposal'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_delta_disposal_invoice}

def _extract_aws_invoice(text: str) -> Optional[str]:
    """AWS invoice extractor"""
    match = re.search(r'Invoice\s*#:?\s*(\d{5,7})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['AWS'] = {'format': 'NNNNNN', 'examples': ['231712'], 'extract': _extract_aws_invoice}

def _extract_matt_s_sanitation_invoice(text: str) -> Optional[str]:
    """Matt's Sanitation invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Matt\'s Sanitation'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_matt_s_sanitation_invoice}

def _extract_marpan_supply_invoice(text: str) -> Optional[str]:
    """Marpan Supply invoice extractor"""
    match = re.search(r'Invoice\s*No\.?:?\s*(\d{6,8})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Marpan Supply'] = {'format': 'NNNNNNN', 'examples': ['1732860'], 'extract': _extract_marpan_supply_invoice}

def _extract_redwood_landfill_invoice(text: str) -> Optional[str]:
    """Redwood Landfill invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Redwood Landfill'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_redwood_landfill_invoice}

def _extract_best_pick_disposal_invoice(text: str) -> Optional[str]:
    """Best Pick Disposal invoice extractor"""
    match = re.search(r'Invoice\s*#:?\s*(\d{5,7})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Best Pick Disposal'] = {'format': 'NNNNNN', 'examples': ['337671'], 'extract': _extract_best_pick_disposal_invoice}

def _extract_bki_recycling_invoice(text: str) -> Optional[str]:
    """BKI Recycling invoice extractor"""
    match = re.search(r'Invoice\s*No\.?:?\s*(\d{5,7})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['BKI Recycling'] = {'format': 'NNNNNN', 'examples': ['201982'], 'extract': _extract_bki_recycling_invoice}

def _extract_city_of_scottsbluff_invoice(text: str) -> Optional[str]:
    """City of Scottsbluff invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['City of Scottsbluff'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_city_of_scottsbluff_invoice}

def _extract_allied_recycling_invoice(text: str) -> Optional[str]:
    """Allied Recycling invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Allied Recycling'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_allied_recycling_invoice}

def _extract_hughes_waste_haulers_invoice(text: str) -> Optional[str]:
    """Hughes Waste Haulers invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Hughes Waste Haulers'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_hughes_waste_haulers_invoice}

def _extract_boston_baler_invoice(text: str) -> Optional[str]:
    """Boston Baler invoice extractor"""
    match = re.search(r'Invoice\s*#:?\s*(\d{4,6})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Boston Baler'] = {'format': 'NNNNN', 'examples': ['43133'], 'extract': _extract_boston_baler_invoice}

def _extract_enviromax_recycling_invoice(text: str) -> Optional[str]:
    """Enviromax Recycling invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Enviromax Recycling'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_enviromax_recycling_invoice}

def _extract_dc_metals_invoice(text: str) -> Optional[str]:
    """DC Metals invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['DC Metals'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_dc_metals_invoice}

def _extract_mac_s_wood_products_invoice(text: str) -> Optional[str]:
    """Mac's Wood Products invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Mac\'s Wood Products'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_mac_s_wood_products_invoice}

def _extract_city_of_kirkland_invoice(text: str) -> Optional[str]:
    """City of Kirkland invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['City of Kirkland'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_city_of_kirkland_invoice}

def _extract_empire_disposal_invoice(text: str) -> Optional[str]:
    """Empire Disposal invoice extractor"""
    match = re.search(r'Invoice\s*No\.?:?\s*(\d{6,8})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Empire Disposal'] = {'format': 'NNNNNNN', 'examples': ['4484585'], 'extract': _extract_empire_disposal_invoice}

def _extract_ma_sanitation_invoice(text: str) -> Optional[str]:
    """MA Sanitation invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['MA Sanitation'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_ma_sanitation_invoice}

def _extract_mountain_high_disposal_invoice(text: str) -> Optional[str]:
    """Mountain High Disposal invoice extractor"""
    match = re.search(r'Invoice\s*#:?\s*(\d{5,7})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Mountain High Disposal'] = {'format': 'NNNNNN', 'examples': ['148866'], 'extract': _extract_mountain_high_disposal_invoice}

def _extract_baker_sanitary_service_invoice(text: str) -> Optional[str]:
    """Baker Sanitary Service invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Baker Sanitary Service'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_baker_sanitary_service_invoice}

def _extract_loren_fischer_disposal_invoice(text: str) -> Optional[str]:
    """Loren Fischer Disposal invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Loren Fischer Disposal'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_loren_fischer_disposal_invoice}

def _extract_kadinger_s_invoice(text: str) -> Optional[str]:
    """Kadinger's invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Kadinger\'s'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_kadinger_s_invoice}

def _extract_dumontelle_waste_invoice(text: str) -> Optional[str]:
    """DuMontelle Waste invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['DuMontelle Waste'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_dumontelle_waste_invoice}

def _extract_mogford_metals_invoice(text: str) -> Optional[str]:
    """Mogford Metals invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Mogford Metals'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_mogford_metals_invoice}

def _extract_emterra_environmental_invoice(text: str) -> Optional[str]:
    """Emterra Environmental invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Emterra Environmental'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_emterra_environmental_invoice}

def _extract_tbs_waste_invoice(text: str) -> Optional[str]:
    """TBS Waste invoice extractor"""
    match = re.search(r'Invoice\s*#:?\s*(\d{9,11})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['TBS Waste'] = {'format': 'NNNNNNNNNN', 'examples': ['2502075417'], 'extract': _extract_tbs_waste_invoice}

def _extract_metalico_youngstown_invoice(text: str) -> Optional[str]:
    """Metalico Youngstown invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Metalico Youngstown'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_metalico_youngstown_invoice}

def _extract_city_of_cartersville_invoice(text: str) -> Optional[str]:
    """City of Cartersville invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['City of Cartersville'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_city_of_cartersville_invoice}

def _extract_ely_disposal_service_invoice(text: str) -> Optional[str]:
    """Ely Disposal Service invoice extractor"""
    match = re.search(r'Invoice\s*Number:?\s*(\d{6,8})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Ely Disposal Service'] = {'format': 'NNNNNNN', 'examples': ['8318043'], 'extract': _extract_ely_disposal_service_invoice}

def _extract_hughes_sons_invoice(text: str) -> Optional[str]:
    """Hughes & Sons invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Hughes & Sons'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_hughes_sons_invoice}

def _extract_jd_parker_invoice(text: str) -> Optional[str]:
    """JD Parker invoice extractor"""
    match = re.search(r'Invoice\s*Number:?\s*(\d{5,7})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['JD Parker'] = {'format': 'NNNNNN', 'examples': ['047612'], 'extract': _extract_jd_parker_invoice}

def _extract_pluffmud_recycling_invoice(text: str) -> Optional[str]:
    """Pluffmud Recycling invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Pluffmud Recycling'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_pluffmud_recycling_invoice}

def _extract_yreka_transfer_invoice(text: str) -> Optional[str]:
    """Yreka Transfer invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Yreka Transfer'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_yreka_transfer_invoice}

def _extract_town_of_lusk_invoice(text: str) -> Optional[str]:
    """Town of Lusk invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Town of Lusk'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_town_of_lusk_invoice}

def _extract_ed_burris_disposal_invoice(text: str) -> Optional[str]:
    """Ed Burris Disposal invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Ed Burris Disposal'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_ed_burris_disposal_invoice}

def _extract_clarke_waste_solutions_invoice(text: str) -> Optional[str]:
    """Clarke Waste Solutions invoice extractor"""
    match = re.search(r'Invoice\s*#:?\s*(\d{4,6})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Clarke Waste Solutions'] = {'format': 'NNNNN', 'examples': ['54295'], 'extract': _extract_clarke_waste_solutions_invoice}

def _extract_cda_garbage_invoice(text: str) -> Optional[str]:
    """CDA Garbage invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['CDA Garbage'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_cda_garbage_invoice}

def _extract_monterey_city_disposal_invoice(text: str) -> Optional[str]:
    """Monterey City Disposal invoice extractor"""
    match = re.search(r'Invoice\s*No\.?:?\s*(\d{9,11})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Monterey City Disposal'] = {'format': 'NNNNNNNNNN', 'examples': ['0001145640'], 'extract': _extract_monterey_city_disposal_invoice}

def _extract_break_it_down_invoice(text: str) -> Optional[str]:
    """Break It Down invoice extractor"""
    match = re.search(r'Invoice\s*No\.?:?\s*(\d{5,7})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Break It Down'] = {'format': 'NNNNNN', 'examples': ['035832'], 'extract': _extract_break_it_down_invoice}

def _extract_industrial_waste_salvage_invoice(text: str) -> Optional[str]:
    """Industrial Waste & Salvage invoice extractor"""
    match = re.search(r'Invoice\s*No\.?:?\s*(\d{9,11})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Industrial Waste & Salvage'] = {'format': 'NNNNNNNNNN', 'examples': ['0001136997'], 'extract': _extract_industrial_waste_salvage_invoice}

def _extract_north_lincoln_sanitary_invoice(text: str) -> Optional[str]:
    """North Lincoln Sanitary invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['North Lincoln Sanitary'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_north_lincoln_sanitary_invoice}

def _extract_city_of_foley_invoice(text: str) -> Optional[str]:
    """City of Foley invoice extractor"""
    match = re.search(r'INV[-\s]?(\d{4,6})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['City of Foley'] = {'format': 'INV-NNNNN', 'examples': ['38448'], 'extract': _extract_city_of_foley_invoice}

def _extract_ace_sanitation_service_invoice(text: str) -> Optional[str]:
    """Ace Sanitation Service invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Ace Sanitation Service'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_ace_sanitation_service_invoice}

def _extract_all_states_rentals_invoice(text: str) -> Optional[str]:
    """All States Rentals invoice extractor"""
    match = re.search(r'Invoice\s*No\.?:?\s*(\d{6,8})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['All States Rentals'] = {'format': 'NNNNNNN', 'examples': ['0245404'], 'extract': _extract_all_states_rentals_invoice}

def _extract_city_of_gainesville_tx_invoice(text: str) -> Optional[str]:
    """City of Gainesville TX invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['City of Gainesville TX'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_city_of_gainesville_tx_invoice}

def _extract_eagle_equipment_service_1_invoice(text: str) -> Optional[str]:
    """Eagle Equipment Service 1 invoice extractor"""
    match = re.search(r'Invoice\s*#:?\s*(\d{4,6})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Eagle Equipment Service 1'] = {'format': 'NNNNN', 'examples': ['16518'], 'extract': _extract_eagle_equipment_service_1_invoice}

def _extract_breezy_hollow_invoice(text: str) -> Optional[str]:
    """Breezy Hollow invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Breezy Hollow'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_breezy_hollow_invoice}

def _extract_alameda_county_industries_invoice(text: str) -> Optional[str]:
    """Alameda County Industries invoice extractor"""
    match = re.search(r'Invoice\s*#:?\s*(\d{9,11})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Alameda County Industries'] = {'format': 'NNNNNNNNNN', 'examples': ['0003791396'], 'extract': _extract_alameda_county_industries_invoice}

def _extract_anaconda_disposal_invoice(text: str) -> Optional[str]:
    """Anaconda Disposal invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Anaconda Disposal'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_anaconda_disposal_invoice}

def _extract_dodd_s_trash_hauling_invoice(text: str) -> Optional[str]:
    """Dodd's Trash Hauling invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Dodd\'s Trash Hauling'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_dodd_s_trash_hauling_invoice}

def _extract_boulder_city_disposal_invoice(text: str) -> Optional[str]:
    """Boulder City Disposal invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Boulder City Disposal'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_boulder_city_disposal_invoice}

def _extract_jdog_junk_removal_invoice(text: str) -> Optional[str]:
    """JDog Junk Removal invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['JDog Junk Removal'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_jdog_junk_removal_invoice}

def _extract_aj_waste_systems_invoice(text: str) -> Optional[str]:
    """AJ Waste Systems invoice extractor"""
    match = re.search(r'Invoice\s*Number:?\s*(\d{5,7})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['AJ Waste Systems'] = {'format': 'NNNNNN', 'examples': ['955832'], 'extract': _extract_aj_waste_systems_invoice}

def _extract_city_of_largo_invoice(text: str) -> Optional[str]:
    """City of Largo invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['City of Largo'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_city_of_largo_invoice}

def _extract_post_environmental_services_invoice(text: str) -> Optional[str]:
    """Post Environmental Services invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Post Environmental Services'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_post_environmental_services_invoice}

def _extract_virgin_valley_disposal_invoice(text: str) -> Optional[str]:
    """Virgin Valley Disposal invoice extractor"""
    match = re.search(r'Invoice\s*#:?\s*(\d{7,9})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Virgin Valley Disposal'] = {'format': 'NNNNNNNN', 'examples': ['44570024'], 'extract': _extract_virgin_valley_disposal_invoice}

def _extract_wm_collection_invoice(text: str) -> Optional[str]:
    """WM Collection invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['WM Collection'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_wm_collection_invoice}

def _extract_american_metal_paper_invoice(text: str) -> Optional[str]:
    """American Metal & Paper invoice extractor"""
    match = re.search(r'Invoice\s*#:?\s*(\d{4,6})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['American Metal & Paper'] = {'format': 'NNNNN', 'examples': ['19335'], 'extract': _extract_american_metal_paper_invoice}

def _extract_all_star_roll_off_invoice(text: str) -> Optional[str]:
    """All Star Roll-Off invoice extractor"""
    match = re.search(r'Invoice\s*#?:?\s*([A-Z]{1,3}[-]?\d{3,6})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['All Star Roll-Off'] = {'format': 'XX-NNN', 'examples': ['I14950'], 'extract': _extract_all_star_roll_off_invoice}

def _extract_city_of_richardson_invoice(text: str) -> Optional[str]:
    """City of Richardson invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['City of Richardson'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_city_of_richardson_invoice}

def _extract_pratt_sanitation_invoice(text: str) -> Optional[str]:
    """Pratt Sanitation invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Pratt Sanitation'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_pratt_sanitation_invoice}

def _extract_advanced_document_solutions_invoice(text: str) -> Optional[str]:
    """Advanced Document Solutions invoice extractor"""
    match = re.search(r'Invoice\s*#:?\s*(\d{7,9})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Advanced Document Solutions'] = {'format': 'NNNNNNNN', 'examples': ['39762357'], 'extract': _extract_advanced_document_solutions_invoice}

def _extract_city_of_hobbs_invoice(text: str) -> Optional[str]:
    """City of Hobbs invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['City of Hobbs'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_city_of_hobbs_invoice}

def _extract_jon_s_refuse_solutions_invoice(text: str) -> Optional[str]:
    """Jon's Refuse Solutions invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Jon\'s Refuse Solutions'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_jon_s_refuse_solutions_invoice}

def _extract_united_waste_haulers_invoice(text: str) -> Optional[str]:
    """United Waste Haulers invoice extractor"""
    match = re.search(r'INV[-\s]?(\d{4,6})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['United Waste Haulers'] = {'format': 'INV-NNNNN', 'examples': ['73509'], 'extract': _extract_united_waste_haulers_invoice}

def _extract_bainbridge_disposal_invoice(text: str) -> Optional[str]:
    """Bainbridge Disposal invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Bainbridge Disposal'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_bainbridge_disposal_invoice}

def _extract_compostnow_invoice(text: str) -> Optional[str]:
    """CompostNow invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['CompostNow'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_compostnow_invoice}

def _extract_marcotte_disposal_invoice(text: str) -> Optional[str]:
    """Marcotte Disposal invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Marcotte Disposal'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_marcotte_disposal_invoice}

def _extract_walker_garbage_and_recycling_invoice(text: str) -> Optional[str]:
    """Walker Garbage and Recycling invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Walker Garbage and Recycling'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_walker_garbage_and_recycling_invoice}

def _extract_city_of_fort_smith_invoice(text: str) -> Optional[str]:
    """City of Fort Smith invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['City of Fort Smith'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_city_of_fort_smith_invoice}

def _extract_c_stoneham_invoice(text: str) -> Optional[str]:
    """C Stoneham invoice extractor"""
    match = re.search(r'Invoice\s*Number:?\s*(\d{4,6})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['C Stoneham'] = {'format': 'NNNNN', 'examples': ['85295'], 'extract': _extract_c_stoneham_invoice}

def _extract_tnr_hauling_invoice(text: str) -> Optional[str]:
    """TNR Hauling invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['TNR Hauling'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_tnr_hauling_invoice}

def _extract_martin_s_trash_service_invoice(text: str) -> Optional[str]:
    """Martin's Trash Service invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Martin\'s Trash Service'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_martin_s_trash_service_invoice}

def _extract_city_of_yuma_invoice(text: str) -> Optional[str]:
    """City of Yuma invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['City of Yuma'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_city_of_yuma_invoice}

def _extract_mills_bros_invoice(text: str) -> Optional[str]:
    """Mills Bros invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Mills Bros'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_mills_bros_invoice}

def _extract_city_of_pleasanton_invoice(text: str) -> Optional[str]:
    """City of Pleasanton invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['City of Pleasanton'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_city_of_pleasanton_invoice}

def _extract_tomorrow_rds_invoice(text: str) -> Optional[str]:
    """Tomorrow RDS invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Tomorrow RDS'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_tomorrow_rds_invoice}

def _extract_city_of_devils_lake_invoice(text: str) -> Optional[str]:
    """City of Devils Lake invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['City of Devils Lake'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_city_of_devils_lake_invoice}

def _extract_georgetown_paper_stock_invoice(text: str) -> Optional[str]:
    """Georgetown Paper Stock invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Georgetown Paper Stock'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_georgetown_paper_stock_invoice}

def _extract_hillsboro_garbage_disposal_invoice(text: str) -> Optional[str]:
    """Hillsboro Garbage Disposal invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Hillsboro Garbage Disposal'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_hillsboro_garbage_disposal_invoice}

def _extract_malcom_enterprises_invoice(text: str) -> Optional[str]:
    """Malcom Enterprises invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Malcom Enterprises'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_malcom_enterprises_invoice}

def _extract_minnkota_recycling_invoice(text: str) -> Optional[str]:
    """Minnkota Recycling invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Minnkota Recycling'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_minnkota_recycling_invoice}

def _extract_reddy_rentals_invoice(text: str) -> Optional[str]:
    """Reddy Rentals invoice extractor"""
    match = re.search(r'Inv\s*#:?\s*(\d{4,6})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Reddy Rentals'] = {'format': 'NNNNN', 'examples': ['40161'], 'extract': _extract_reddy_rentals_invoice}

def _extract_city_of_tullahoma_invoice(text: str) -> Optional[str]:
    """City of Tullahoma invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['City of Tullahoma'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_city_of_tullahoma_invoice}

def _extract_city_of_loganville_invoice(text: str) -> Optional[str]:
    """City of Loganville invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['City of Loganville'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_city_of_loganville_invoice}

def _extract_davis_disposal_invoice(text: str) -> Optional[str]:
    """Davis Disposal invoice extractor"""
    match = re.search(r'Invoice\s*Number:?\s*(\d{9,11})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Davis Disposal'] = {'format': 'NNNNNNNNNN', 'examples': ['2507110635'], 'extract': _extract_davis_disposal_invoice}

def _extract_ewe_equipment_invoice(text: str) -> Optional[str]:
    """EWE Equipment invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['EWE Equipment'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_ewe_equipment_invoice}

def _extract_pak_rite_rentals_invoice(text: str) -> Optional[str]:
    """Pak-Rite Rentals invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Pak-Rite Rentals'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_pak_rite_rentals_invoice}

def _extract_loren_s_sanitation_invoice(text: str) -> Optional[str]:
    """Loren's Sanitation invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Loren\'s Sanitation'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_loren_s_sanitation_invoice}

def _extract_town_of_greeneville_invoice(text: str) -> Optional[str]:
    """Town of Greeneville invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Town of Greeneville'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_town_of_greeneville_invoice}

def _extract_weiner_iron_metal_invoice(text: str) -> Optional[str]:
    """Weiner Iron & Metal invoice extractor"""
    match = re.search(r'Invoice\s*Number:?\s*(\d{6,8})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Weiner Iron & Metal'] = {'format': 'NNNNNNN', 'examples': ['0014732'], 'extract': _extract_weiner_iron_metal_invoice}

def _extract_ctl_3r_technology_invoice(text: str) -> Optional[str]:
    """CTL 3R Technology invoice extractor"""
    match = re.search(r'INV[-\s]?(\d{4,6})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['CTL 3R Technology'] = {'format': 'INV-NNNNN', 'examples': ['18460'], 'extract': _extract_ctl_3r_technology_invoice}

def _extract_flash_trash_invoice(text: str) -> Optional[str]:
    """Flash Trash invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Flash Trash'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_flash_trash_invoice}

def _extract_r_r_recycling_inc_invoice(text: str) -> Optional[str]:
    """R&R Recycling Inc invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['R&R Recycling Inc'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_r_r_recycling_inc_invoice}

def _extract_besttrash_invoice(text: str) -> Optional[str]:
    """BestTrash invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['BestTrash'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_besttrash_invoice}

def _extract_crown_waste_recycling_invoice(text: str) -> Optional[str]:
    """Crown Waste & Recycling invoice extractor"""
    match = re.search(r'Invoice\s*#:?\s*(\d{4,6})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Crown Waste & Recycling'] = {'format': 'NNNNN', 'examples': ['74629'], 'extract': _extract_crown_waste_recycling_invoice}

def _extract_standing_rock_sanitation_invoice(text: str) -> Optional[str]:
    """Standing Rock Sanitation invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Standing Rock Sanitation'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_standing_rock_sanitation_invoice}

def _extract_sos_waste_disposal_invoice(text: str) -> Optional[str]:
    """SOS Waste Disposal invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['SOS Waste Disposal'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_sos_waste_disposal_invoice}

def _extract_wemiga_waste_invoice(text: str) -> Optional[str]:
    """Wemiga Waste invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Wemiga Waste'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_wemiga_waste_invoice}

def _extract_david_s_trash_service_invoice(text: str) -> Optional[str]:
    """David's Trash Service invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['David\'s Trash Service'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_david_s_trash_service_invoice}

def _extract_sweetland_invoice(text: str) -> Optional[str]:
    """Sweetland invoice extractor"""
    match = re.search(r'Invoice\s*#:?\s*(\d{4,6})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Sweetland'] = {'format': 'NNNNN', 'examples': ['20170'], 'extract': _extract_sweetland_invoice}

def _extract_city_lakes_disposal_invoice(text: str) -> Optional[str]:
    """City & Lakes Disposal invoice extractor"""
    match = re.search(r'Invoice\s*#:?\s*(\d{7,9})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['City & Lakes Disposal'] = {'format': 'NNNNNNNN', 'examples': ['56102948'], 'extract': _extract_city_lakes_disposal_invoice}

def _extract_chum_refuse_invoice(text: str) -> Optional[str]:
    """Chum Refuse invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Chum Refuse'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_chum_refuse_invoice}

def _extract_city_of_enumclaw_invoice(text: str) -> Optional[str]:
    """City of Enumclaw invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['City of Enumclaw'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_city_of_enumclaw_invoice}

def _extract_adam_s_disposal_invoice(text: str) -> Optional[str]:
    """Adam's Disposal invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Adam\'s Disposal'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_adam_s_disposal_invoice}

def _extract_city_of_barstow_invoice(text: str) -> Optional[str]:
    """City of Barstow invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['City of Barstow'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_city_of_barstow_invoice}

def _extract_brothers_disposal_invoice(text: str) -> Optional[str]:
    """Brothers Disposal invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Brothers Disposal'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_brothers_disposal_invoice}

def _extract_golden_eagle_services_invoice(text: str) -> Optional[str]:
    """Golden Eagle Services invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Golden Eagle Services'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_golden_eagle_services_invoice}

def _extract_sustainable_environmental_management_invoice(text: str) -> Optional[str]:
    """Sustainable Environmental Management invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Sustainable Environmental Management'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_sustainable_environmental_management_invoice}

def _extract_civicorps_recycling_invoice(text: str) -> Optional[str]:
    """Civicorps Recycling invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Civicorps Recycling'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_civicorps_recycling_invoice}

def _extract_hamilton_recycling_disposal_invoice(text: str) -> Optional[str]:
    """Hamilton Recycling Disposal invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Hamilton Recycling Disposal'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_hamilton_recycling_disposal_invoice}

def _extract_johnson_city_utility_invoice(text: str) -> Optional[str]:
    """Johnson City Utility invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Johnson City Utility'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_johnson_city_utility_invoice}

def _extract_first_capitol_salvage_invoice(text: str) -> Optional[str]:
    """First Capitol Salvage invoice extractor"""
    match = re.search(r'Invoice\s*Number:?\s*(\d{5,7})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['First Capitol Salvage'] = {'format': 'NNNNNN', 'examples': ['017510'], 'extract': _extract_first_capitol_salvage_invoice}

def _extract_p_s_trucking_invoice(text: str) -> Optional[str]:
    """P&S Trucking invoice extractor"""
    match = re.search(r'Invoice\s*#:?\s*(\d{5,7})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['P&S Trucking'] = {'format': 'NNNNNN', 'examples': ['000645'], 'extract': _extract_p_s_trucking_invoice}

def _extract_sutherlin_sanitary_invoice(text: str) -> Optional[str]:
    """Sutherlin Sanitary invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Sutherlin Sanitary'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_sutherlin_sanitary_invoice}

def _extract_excess_disposal_invoice(text: str) -> Optional[str]:
    """Excess Disposal invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Excess Disposal'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_excess_disposal_invoice}

def _extract_city_of_socorro_invoice(text: str) -> Optional[str]:
    """City of Socorro invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['City of Socorro'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_city_of_socorro_invoice}

def _extract_dirty_boyz_sanitation_invoice(text: str) -> Optional[str]:
    """Dirty Boyz Sanitation invoice extractor"""
    match = re.search(r'Invoice\s*#:?\s*(\d{5,7})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Dirty Boyz Sanitation'] = {'format': 'NNNNNN', 'examples': ['163096'], 'extract': _extract_dirty_boyz_sanitation_invoice}

def _extract_maxshred_invoice(text: str) -> Optional[str]:
    """MaxShred invoice extractor"""
    match = re.search(r'Invoice\s*#:?\s*(\d{4,6})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['MaxShred'] = {'format': 'NNNNN', 'examples': ['86255'], 'extract': _extract_maxshred_invoice}

def _extract_cliff_s_commercial_trash_invoice(text: str) -> Optional[str]:
    """Cliff's Commercial Trash invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Cliff\'s Commercial Trash'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_cliff_s_commercial_trash_invoice}

def _extract_d_d_refuse_invoice(text: str) -> Optional[str]:
    """D & D Refuse invoice extractor"""
    match = re.search(r'Invoice\s*#:?\s*(\d{9,11})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['D & D Refuse'] = {'format': 'NNNNNNNNNN', 'examples': ['2507302174'], 'extract': _extract_d_d_refuse_invoice}

def _extract_j_j_sanitation_invoice(text: str) -> Optional[str]:
    """J&J Sanitation invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['J&J Sanitation'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_j_j_sanitation_invoice}

def _extract_srg_spartanburg_invoice(text: str) -> Optional[str]:
    """SRG Spartanburg invoice extractor"""
    match = re.search(r'Invoice\s*#?:?\s*([A-Z]{1,3}[-]?\d{3,6})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['SRG Spartanburg'] = {'format': 'XX-NNN', 'examples': ['D48774'], 'extract': _extract_srg_spartanburg_invoice}

def _extract_kept_companies_invoice(text: str) -> Optional[str]:
    """Kept Companies invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Kept Companies'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_kept_companies_invoice}

def _extract_white_mountain_apache_invoice(text: str) -> Optional[str]:
    """White Mountain Apache invoice extractor"""
    match = re.search(r'Invoice\s*#?:?\s*([A-Z]{1,3}[-]?\d{5,8})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['White Mountain Apache'] = {'format': 'XX-NNNNN', 'examples': ['SW021976'], 'extract': _extract_white_mountain_apache_invoice}

def _extract_evergreen_paper_recycling_invoice(text: str) -> Optional[str]:
    """Evergreen Paper Recycling invoice extractor"""
    match = re.search(r'Invoice\s*No\.?:?\s*(\d{5,7})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Evergreen Paper Recycling'] = {'format': 'NNNNNN', 'examples': ['149136'], 'extract': _extract_evergreen_paper_recycling_invoice}

def _extract_moon_companies_invoice(text: str) -> Optional[str]:
    """Moon Companies invoice extractor"""
    match = re.search(r'Invoice\s*#:?\s*(\d{4,6})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Moon Companies'] = {'format': 'NNNNN', 'examples': ['66509'], 'extract': _extract_moon_companies_invoice}

def _extract_rahn_sanitary_invoice(text: str) -> Optional[str]:
    """Rahn Sanitary invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Rahn Sanitary'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_rahn_sanitary_invoice}

def _extract_iron_mountain_invoice(text: str) -> Optional[str]:
    """Iron Mountain invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Iron Mountain'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_iron_mountain_invoice}

def _extract_kaibab_band_invoice(text: str) -> Optional[str]:
    """Kaibab Band invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Kaibab Band'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_kaibab_band_invoice}

def _extract_c_h_disposal_invoice(text: str) -> Optional[str]:
    """C & H Disposal invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['C & H Disposal'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_c_h_disposal_invoice}

def _extract_town_of_wickenburg_invoice(text: str) -> Optional[str]:
    """Town of Wickenburg invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Town of Wickenburg'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_town_of_wickenburg_invoice}

def _extract_maguire_equipment_invoice(text: str) -> Optional[str]:
    """Maguire Equipment invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Maguire Equipment'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_maguire_equipment_invoice}

def _extract_fisk_waste_removal_invoice(text: str) -> Optional[str]:
    """Fisk Waste Removal invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Fisk Waste Removal'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_fisk_waste_removal_invoice}

def _extract_city_of_grand_junction_invoice(text: str) -> Optional[str]:
    """City of Grand Junction invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['City of Grand Junction'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_city_of_grand_junction_invoice}

def _extract_town_of_dutch_john_invoice(text: str) -> Optional[str]:
    """Town of Dutch John invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Town of Dutch John'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_town_of_dutch_john_invoice}

def _extract_waste_recycling_inc_invoice(text: str) -> Optional[str]:
    """Waste Recycling Inc invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Waste Recycling Inc'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_waste_recycling_inc_invoice}

def _extract_ultimate_specialties_invoice(text: str) -> Optional[str]:
    """Ultimate Specialties invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Ultimate Specialties'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_ultimate_specialties_invoice}

def _extract_cook_sanitation_invoice(text: str) -> Optional[str]:
    """Cook Sanitation invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Cook Sanitation'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_cook_sanitation_invoice}

def _extract_eagle_equipment_corporation_invoice(text: str) -> Optional[str]:
    """Eagle Equipment Corporation invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Eagle Equipment Corporation'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_eagle_equipment_corporation_invoice}

def _extract_big_bear_disposal_invoice(text: str) -> Optional[str]:
    """Big Bear Disposal invoice extractor"""
    match = re.search(r'Invoice\s*No\.?:?\s*(\d{9,11})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Big Bear Disposal'] = {'format': 'NNNNNNNNNN', 'examples': ['0000119946'], 'extract': _extract_big_bear_disposal_invoice}

def _extract_city_of_lake_mary_invoice(text: str) -> Optional[str]:
    """City of Lake Mary invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['City of Lake Mary'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_city_of_lake_mary_invoice}

def _extract_lci_services_invoice(text: str) -> Optional[str]:
    """LCI Services invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['LCI Services'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_lci_services_invoice}

def _extract_city_of_del_rio_invoice(text: str) -> Optional[str]:
    """City of Del Rio invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['City of Del Rio'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_city_of_del_rio_invoice}

def _extract_hudgins_disposal_invoice(text: str) -> Optional[str]:
    """Hudgins Disposal invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Hudgins Disposal'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_hudgins_disposal_invoice}

def _extract_generated_materials_recovery_invoice(text: str) -> Optional[str]:
    """Generated Materials Recovery invoice extractor"""
    match = re.search(r'Invoice\s*#:?\s*(\d{4,6})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Generated Materials Recovery'] = {'format': 'NNNNN', 'examples': ['47957'], 'extract': _extract_generated_materials_recovery_invoice}

def _extract_hopper_disposal_invoice(text: str) -> Optional[str]:
    """Hopper Disposal invoice extractor"""
    match = re.search(r'Inv\s*#:?\s*(\d{4,6})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Hopper Disposal'] = {'format': 'NNNNN', 'examples': ['30392'], 'extract': _extract_hopper_disposal_invoice}

def _extract_bcda_the_trash_company_invoice(text: str) -> Optional[str]:
    """BCDA The Trash Company invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['BCDA The Trash Company'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_bcda_the_trash_company_invoice}

def _extract_desert_valley_disposal_invoice(text: str) -> Optional[str]:
    """Desert Valley Disposal invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Desert Valley Disposal'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_desert_valley_disposal_invoice}

def _extract_mcs_midwest_invoice(text: str) -> Optional[str]:
    """MCS Midwest invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['MCS Midwest'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_mcs_midwest_invoice}

def _extract_pleasanton_garbage_invoice(text: str) -> Optional[str]:
    """Pleasanton Garbage invoice extractor"""
    match = re.search(r'Invoice\s*No\.?:?\s*(\d{9,11})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Pleasanton Garbage'] = {'format': 'NNNNNNNNNN', 'examples': ['0000731201'], 'extract': _extract_pleasanton_garbage_invoice}

def _extract_styro_recycle_invoice(text: str) -> Optional[str]:
    """Styro Recycle invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Styro Recycle'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_styro_recycle_invoice}

def _extract_solid_waste_disposal_authority_invoice(text: str) -> Optional[str]:
    """Solid Waste Disposal Authority invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Solid Waste Disposal Authority'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_solid_waste_disposal_authority_invoice}

def _extract_buldo_container_disposal_invoice(text: str) -> Optional[str]:
    """Buldo Container & Disposal invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Buldo Container & Disposal'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_buldo_container_disposal_invoice}

def _extract_mcallen_public_utility_invoice(text: str) -> Optional[str]:
    """McAllen Public Utility invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['McAllen Public Utility'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_mcallen_public_utility_invoice}

def _extract_desert_green_disposal_invoice(text: str) -> Optional[str]:
    """Desert Green Disposal invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Desert Green Disposal'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_desert_green_disposal_invoice}

def _extract_city_of_lamar_invoice(text: str) -> Optional[str]:
    """City of Lamar invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['City of Lamar'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_city_of_lamar_invoice}

def _extract_capital_area_refuse_invoice(text: str) -> Optional[str]:
    """Capital Area Refuse invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Capital Area Refuse'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_capital_area_refuse_invoice}

def _extract_main_street_fibers_invoice(text: str) -> Optional[str]:
    """Main Street Fibers invoice extractor"""
    match = re.search(r'Invoice\s*#:?\s*(\d{4,6})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Main Street Fibers'] = {'format': 'NNNNN', 'examples': ['68866'], 'extract': _extract_main_street_fibers_invoice}

def _extract_city_of_lebanon_invoice(text: str) -> Optional[str]:
    """City of Lebanon invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['City of Lebanon'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_city_of_lebanon_invoice}

def _extract_liberty_ashes_invoice(text: str) -> Optional[str]:
    """Liberty Ashes invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Liberty Ashes'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_liberty_ashes_invoice}

def _extract_kluesner_sanitation_invoice(text: str) -> Optional[str]:
    """Kluesner Sanitation invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Kluesner Sanitation'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_kluesner_sanitation_invoice}

def _extract_my_green_michigan_invoice(text: str) -> Optional[str]:
    """My Green Michigan invoice extractor"""
    match = re.search(r'Invoice\s*No\.?:?\s*(\d{5,7})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['My Green Michigan'] = {'format': 'NNNNNN', 'examples': ['138414'], 'extract': _extract_my_green_michigan_invoice}

def _extract_mauldin_trash_invoice(text: str) -> Optional[str]:
    """Mauldin Trash invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Mauldin Trash'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_mauldin_trash_invoice}

def _extract_big_river_disposal_invoice(text: str) -> Optional[str]:
    """Big River Disposal invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Big River Disposal'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_big_river_disposal_invoice}

def _extract_g_h_garbage_invoice(text: str) -> Optional[str]:
    """G & H Garbage invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['G & H Garbage'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_g_h_garbage_invoice}

def _extract_seagraves_plumbing_invoice(text: str) -> Optional[str]:
    """Seagraves Plumbing invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Seagraves Plumbing'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_seagraves_plumbing_invoice}

def _extract_american_hauling_services_invoice(text: str) -> Optional[str]:
    """American Hauling Services invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['American Hauling Services'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_american_hauling_services_invoice}

def _extract_lakeside_recycling_invoice(text: str) -> Optional[str]:
    """Lakeside Recycling invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Lakeside Recycling'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_lakeside_recycling_invoice}

def _extract_redfish_recycling_invoice(text: str) -> Optional[str]:
    """Redfish Recycling invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Redfish Recycling'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_redfish_recycling_invoice}

def _extract_carrier_container_invoice(text: str) -> Optional[str]:
    """Carrier Container invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Carrier Container'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_carrier_container_invoice}

def _extract_d_s_waste_invoice(text: str) -> Optional[str]:
    """D&S Waste invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['D&S Waste'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_d_s_waste_invoice}

def _extract_ljp_waste_invoice(text: str) -> Optional[str]:
    """LJP Waste invoice extractor"""
    match = re.search(r'Invoice\s*#:?\s*(\d{5,7})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['LJP Waste'] = {'format': 'NNNNNN', 'examples': ['304304'], 'extract': _extract_ljp_waste_invoice}

def _extract_hesco_hydraulic_invoice(text: str) -> Optional[str]:
    """HESCO Hydraulic invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['HESCO Hydraulic'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_hesco_hydraulic_invoice}

def _extract_columbia_county_solid_waste_invoice(text: str) -> Optional[str]:
    """Columbia County Solid Waste invoice extractor"""
    match = re.search(r'Invoice\s*#:?\s*(\d{4,6})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Columbia County Solid Waste'] = {'format': 'NNNNN', 'examples': ['46337'], 'extract': _extract_columbia_county_solid_waste_invoice}

def _extract_city_of_henagar_invoice(text: str) -> Optional[str]:
    """City of Henagar invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['City of Henagar'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_city_of_henagar_invoice}

def _extract_thomas_trash_invoice(text: str) -> Optional[str]:
    """Thomas Trash invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Thomas Trash'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_thomas_trash_invoice}

def _extract_waste_partners_invoice(text: str) -> Optional[str]:
    """Waste Partners invoice extractor"""
    match = re.search(r'Invoice\s*#:?\s*(\d{7,9})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Waste Partners'] = {'format': 'NNNNNNNN', 'examples': ['55103283'], 'extract': _extract_waste_partners_invoice}

def _extract_tate_services_invoice(text: str) -> Optional[str]:
    """Tate Services invoice extractor"""
    match = re.search(r'Invoice\s*No\.?:?\s*(\d{9,11})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Tate Services'] = {'format': 'NNNNNNNNNN', 'examples': ['0000235059'], 'extract': _extract_tate_services_invoice}

def _extract_town_of_babylon_invoice(text: str) -> Optional[str]:
    """Town of Babylon invoice extractor"""
    match = re.search(r'Invoice\s*#:?\s*(\d{9,11})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Town of Babylon'] = {'format': 'NNNNNNNNNN', 'examples': ['0001563011'], 'extract': _extract_town_of_babylon_invoice}

def _extract_local_waste_of_upstate_invoice(text: str) -> Optional[str]:
    """Local Waste of Upstate invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Local Waste of Upstate'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_local_waste_of_upstate_invoice}

def _extract_fritz_enterprises_invoice(text: str) -> Optional[str]:
    """Fritz Enterprises invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Fritz Enterprises'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_fritz_enterprises_invoice}

def _extract_harley_hollan_invoice(text: str) -> Optional[str]:
    """Harley Hollan invoice extractor"""
    match = re.search(r'Invoice\s*#:?\s*(\d{5,7})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Harley Hollan'] = {'format': 'NNNNNN', 'examples': ['799723'], 'extract': _extract_harley_hollan_invoice}

def _extract_island_recycling_invoice(text: str) -> Optional[str]:
    """Island Recycling invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Island Recycling'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_island_recycling_invoice}

def _extract_sphuler_disposal_invoice(text: str) -> Optional[str]:
    """Sphuler Disposal invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Sphuler Disposal'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_sphuler_disposal_invoice}

def _extract_brookings_dumpster_service_invoice(text: str) -> Optional[str]:
    """Brookings Dumpster Service invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Brookings Dumpster Service'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_brookings_dumpster_service_invoice}

def _extract_harper_sanitation_invoice(text: str) -> Optional[str]:
    """Harper Sanitation invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Harper Sanitation'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_harper_sanitation_invoice}

def _extract_s_b_cox_invoice(text: str) -> Optional[str]:
    """S.B. Cox invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['S.B. Cox'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_s_b_cox_invoice}

def _extract_t_s_trash_service_invoice(text: str) -> Optional[str]:
    """T & S Trash Service invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['T & S Trash Service'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_t_s_trash_service_invoice}

def _extract_blue_compactor_invoice(text: str) -> Optional[str]:
    """Blue Compactor invoice extractor"""
    match = re.search(r'Invoice\s*No\.?:?\s*(\d{7,9})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Blue Compactor'] = {'format': 'NNNNNNNN', 'examples': ['12620013'], 'extract': _extract_blue_compactor_invoice}

def _extract_franklin_disposal_invoice(text: str) -> Optional[str]:
    """Franklin Disposal invoice extractor"""
    match = re.search(r'Invoice\s*#?:?\s*([A-Z]{1,3}[-]?\d{6,9})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Franklin Disposal'] = {'format': 'XX-NNNNNN', 'examples': ['chz133752'], 'extract': _extract_franklin_disposal_invoice}

def _extract_revolution_recycling_invoice(text: str) -> Optional[str]:
    """Revolution Recycling invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Revolution Recycling'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_revolution_recycling_invoice}

def _extract_brew_crew_environmental_invoice(text: str) -> Optional[str]:
    """Brew Crew Environmental invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Brew Crew Environmental'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_brew_crew_environmental_invoice}

def _extract_teg_lease_invoice(text: str) -> Optional[str]:
    """TEG Lease invoice extractor"""
    match = re.search(r'Invoice\s*Number:?\s*(\d{5,7})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['TEG Lease'] = {'format': 'NNNNNN', 'examples': ['784820'], 'extract': _extract_teg_lease_invoice}

def _extract_c_b_sanitary_invoice(text: str) -> Optional[str]:
    """C & B Sanitary invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['C & B Sanitary'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_c_b_sanitary_invoice}

def _extract_mercer_group_invoice(text: str) -> Optional[str]:
    """Mercer Group invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Mercer Group'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_mercer_group_invoice}

def _extract_total_waste_management_invoice(text: str) -> Optional[str]:
    """Total Waste Management invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Total Waste Management'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_total_waste_management_invoice}

def _extract_nw_dumpsters_invoice(text: str) -> Optional[str]:
    """NW Dumpsters invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['NW Dumpsters'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_nw_dumpsters_invoice}

def _extract_ken_s_sanitation_invoice(text: str) -> Optional[str]:
    """Ken's Sanitation invoice extractor"""
    match = re.search(r'Inv\s*#:?\s*(\d{5,7})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Ken\'s Sanitation'] = {'format': 'NNNNNN', 'examples': ['399181'], 'extract': _extract_ken_s_sanitation_invoice}

def _extract_long_island_waste_invoice(text: str) -> Optional[str]:
    """Long Island Waste invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Long Island Waste'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_long_island_waste_invoice}

def _extract_miller_waste_systems_invoice(text: str) -> Optional[str]:
    """Miller Waste Systems invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Miller Waste Systems'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_miller_waste_systems_invoice}

def _extract_montgomery_county_environmental_invoice(text: str) -> Optional[str]:
    """Montgomery County Environmental invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Montgomery County Environmental'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_montgomery_county_environmental_invoice}

def _extract_mcdowell_sons_sanitation_invoice(text: str) -> Optional[str]:
    """McDowell & Sons Sanitation invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['McDowell & Sons Sanitation'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_mcdowell_sons_sanitation_invoice}

def _extract_upper_valley_disposal_invoice(text: str) -> Optional[str]:
    """Upper Valley Disposal invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Upper Valley Disposal'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_upper_valley_disposal_invoice}

def _extract_tri_state_carting_invoice(text: str) -> Optional[str]:
    """Tri-State Carting invoice extractor"""
    match = re.search(r'Invoice\s*#:?\s*(\d{5,7})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Tri-State Carting'] = {'format': 'NNNNNN', 'examples': ['676125'], 'extract': _extract_tri_state_carting_invoice}

def _extract_hillsborough_county_sw_invoice(text: str) -> Optional[str]:
    """Hillsborough County SW invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Hillsborough County SW'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_hillsborough_county_sw_invoice}

def _extract_j_b_disposal_invoice(text: str) -> Optional[str]:
    """J & B Disposal invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['J & B Disposal'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_j_b_disposal_invoice}

def _extract_happen_ventures_invoice(text: str) -> Optional[str]:
    """Happen Ventures invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Happen Ventures'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_happen_ventures_invoice}

def _extract_city_of_green_river_invoice(text: str) -> Optional[str]:
    """City of Green River invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['City of Green River'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_city_of_green_river_invoice}

def _extract_southland_environmental_invoice(text: str) -> Optional[str]:
    """Southland Environmental invoice extractor"""
    match = re.search(r'Invoice\s*#:?\s*(\d{7,9})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Southland Environmental'] = {'format': 'NNNNNNNN', 'examples': ['55101384'], 'extract': _extract_southland_environmental_invoice}

def _extract_jazme_invoice(text: str) -> Optional[str]:
    """Jazme invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Jazme'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_jazme_invoice}

def _extract_501_sanitation_invoice(text: str) -> Optional[str]:
    """501 Sanitation invoice extractor"""
    match = re.search(r'Invoice\s*No\.?:?\s*(\d{4,6})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['501 Sanitation'] = {'format': 'NNNNN', 'examples': ['15723'], 'extract': _extract_501_sanitation_invoice}

def _extract_arrow_waste_invoice(text: str) -> Optional[str]:
    """Arrow Waste invoice extractor"""
    match = re.search(r'Invoice\s*#:?\s*(\d{5,7})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Arrow Waste'] = {'format': 'NNNNNN', 'examples': ['153419'], 'extract': _extract_arrow_waste_invoice}

def _extract_far_west_recycling_invoice(text: str) -> Optional[str]:
    """Far West Recycling invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Far West Recycling'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_far_west_recycling_invoice}

def _extract_countrywide_sanitation_invoice(text: str) -> Optional[str]:
    """Countrywide Sanitation invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Countrywide Sanitation'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_countrywide_sanitation_invoice}

def _extract_j_m_sanitation_invoice(text: str) -> Optional[str]:
    """J & M Sanitation invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['J & M Sanitation'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_j_m_sanitation_invoice}

def _extract_waste_collection_services_invoice(text: str) -> Optional[str]:
    """Waste Collection Services invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Waste Collection Services'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_waste_collection_services_invoice}

def _extract_zero_waste_invoice(text: str) -> Optional[str]:
    """Zero Waste invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['Zero Waste'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_zero_waste_invoice}

def _extract_dkmm_solid_waste_invoice(text: str) -> Optional[str]:
    """DKMM Solid Waste invoice extractor"""
    match = re.search(r'Invoice\s*(?:#|Number|No\.?)?:?\s*(\d{5,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_INVOICES['DKMM Solid Waste'] = {'format': 'NNNNNN', 'examples': [''], 'extract': _extract_dkmm_solid_waste_invoice}


# ============================================================
# AUTO-IMPORT ADDITIONS (must be AFTER all vendor registrations)
# ============================================================

try:
    from invoice_number.invoice_extraction_additions_feb2026 import register_additions
    register_additions(VENDOR_INVOICES)
except ImportError:
    try:
        from invoice_extraction_additions_feb2026 import register_additions
        register_additions(VENDOR_INVOICES)
    except ImportError:
        pass
