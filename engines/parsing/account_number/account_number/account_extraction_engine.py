"""
Account Number Extraction Engine v5.0
Extracts customer account numbers from invoice OCR text.

Designed to work with vendor_detection_module.py as part of deterministic 
invoice matching pipeline.

Usage:
    1. First detect vendor using vendor_detection_module.detect_vendor()
    2. Then extract account using extract_account(vendor_name, text)

DETERMINISTIC RULES:
- Each vendor has explicit extraction logic
- Returns account number OR None (no guessing)
- Pattern must match exactly or extraction fails

V5 FINAL RESULTS: 97.8% extraction rate (2,433/2,488 invoices)

TRANCHE 2 (14 vendors, +865 invoices):
- ABC Waste: 98.5% (NN-NNNN N check digit format)
- Smith Creek: 98.5% (WASTNNN format)
- JLT Trucking: 100% (7-digit, portal format)
- Liberty Disposal: 92.2% (scale tickets + invoices, mixed formats)
  * 5 failures are announcements/agreements, not invoices
- ZARC Recycling: 100% (3-digit Customer ID)
- 1-800-Got-Junk: 98.4% (3-digit Customer ID, columnar)
- Ryland Environmental: 56.5% raw / 100% actual invoices
  * 19 are Transaction Receipts (no account expected)
  * 8 are WM misdetections (vendor detection issue)
- Independent Recycling: 95.2% (4-digit CUSTOMER NO)
- Moore Coal: 100% (4-digit CUSTOMER NO)
- Honolulu Disposal: 94.9% (8-10 digit)
  * 3 failures are holiday/notices, not invoices
- Pelican Waste: 96.6% (6-digit)
- NO_ACCOUNT: Conigliaro, D Crescio Trucking, Premier Waste

TRANCHE 1 (11 vendors, +1,960 invoices):
- Cockey's Enterprises: 99.9% (NNNNN)
- Harter's: 96.6% (NN-NNNNN N / NNNNNN)
- City of Meridian: 100% (NNNNNNNN-NN)
- Blue Diamond Disposal: 100% (NNNNN)
- Valley Vista: 97.1% (VV-/VC- prefixes)
- SSW Frontload: 100% (TrashBilling)
- Velpen Trucking: 100% (TrashBilling)
- Gotta Go Waste: 95.5% (NNNN)
  * 3 failures are "Zach Erwin Construction" (different company)
- Louisiana Waste: 100% (NNNN)
- NO_ACCOUNT: Becker360, Pete & Pete

V4 CHANGES (December 2024) - New Tranche (17 vendors):
- Boro Wide: 100% (LBP-NNNNNN / BP-NNNNNN / NN-NNNNNNN)
- Direct Waste Services: 95.5% (4-digit)
- Cards Mo: 97.7% (NN-NNNNN N)
- Chrin Hauling: 100% (6-digit)
- Roll Off Systems: 100% (6-digit)
- Lakeshore Recycling: 97.7% (NNNNN.N or NNNNN)
- Cooks Wastepaper: 100% (DDDD-NNNNNN WC format)
- EOMS Recycling: 95.2% (12-digit TrashBilling)
- Mid Valley Disposal: 95.1% (8-digit)
- Modern Corporation: 100% (5-digit)
- Atlantic Waste: 100% (9-digit)
- Vista Recycling: 95.1% (7-digit)
- Ace Waste Systems: 100% (NN-NNNNN N)
- Schaap Sanitation: 100% (DDDD-NNNNNN WC format)
- Waste Services LLC: TrashBilling branch only
- NO_ACCOUNT: Advance Machine & Hydraulic, Green Guys

V3 CHANGES (December 2024):
- Anytime Waste, Universal Waste, Robinson Waste, Casella improved to 95%+
- FCC Environmental: Multiple regional formats
- Lightning Disposal, All Waste, Tiger Sanitation fixed

Maintained by: Wasteology
Last updated: December 2024
"""
import re
from typing import Optional, Dict, Any, List, Tuple

# ============================================================
# VENDOR ACCOUNT CONFIGURATIONS
# ============================================================


# ============================================================
# FIXED EXTRACTION FUNCTIONS (v3 - December 2024)
# ============================================================

def _extract_ace_recycling_v3(text):
    """Format: 5-6 digit after ACCOUNT # header or on same line
    V4 FIX: Added same-line extraction for NG invoices (ACCOUNT # 801916)
    """
    # Format 1: Same line - ACCOUNT # NNNNNN
    match = re.search(r'ACCOUNT\s*#\s*(\d{5,6})\b', text, re.I)
    if match:
        return match.group(1)

    # Format 2: Separate lines - ACCOUNT #\nNNNNNN
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if 'ACCOUNT #' in line.upper():
            for j in range(i+1, min(i+5, len(lines))):
                val = lines[j].strip()
                if re.match(r'^\d{5,6}$', val):
                    return val
    return None

def _extract_metalpro_v3(text):
    """Format: State+4 digits (MD0606) OR 5 digits (13117)"""
    if 'METALPRO' not in text.upper():
        return None
    match = re.search(r'Customer\s*Number:\s*([A-Z]{2}\d{4}|\d{5})', text)
    if match:
        return match.group(1)
    lines = text.split('\\n')
    for i, line in enumerate(lines):
        if 'Customer Number' in line:
            m = re.search(r'Customer\s*Number:\s*([A-Z]{2}\d{4}|\d{4,5})', line)
            if m:
                return m.group(1)
            for j in range(i+1, min(i+4, len(lines))):
                m = re.match(r'^([A-Z]{2}\d{4}|\d{4,5})$', lines[j].strip())
                if m:
                    return m.group(1)
    return None

def _extract_texas_disposal_v3(text):
    """Format: D-NNNNNN or D-NNNN (several lines after Customer Number)"""
    lines = text.split('\\n')
    for i, line in enumerate(lines):
        if 'Customer Number' in line:
            for j in range(i, min(i+10, len(lines))):
                m = re.search(r'^(\d-\d{4,6})$', lines[j].strip())
                if m:
                    return m.group(1)
    return None

def _extract_ankeny_sanitation_v3(text):
    """Format: NN-NNNNNN N (Customer #)"""
    match = re.search(r'Customer\s*#:\s*(\d{2}-\d{6}\s*\d)', text, re.I)
    if match:
        return match.group(1).strip()
    return None

def _extract_basin_disposal_v3(text):
    """Format: 7-digit or NN-NNNNNN N (Texas branch)"""
    match = re.search(r'Account\s*Number\\n(\d{7})', text)
    if match:
        return match.group(1)
    lines = text.split('\\n')
    for i, line in enumerate(lines):
        if 'Customer Number' in line:
            for j in range(i+1, min(i+8, len(lines))):
                m = re.match(r'^(\d{2}-\d{6}\s*\d)$', lines[j].strip())
                if m:
                    return m.group(1).strip()
    for i, line in enumerate(lines):
        if 'Account:' in line:
            for j in range(i, min(i+6, len(lines))):
                if re.match(r'^\d{7}$', lines[j].strip()):
                    return lines[j].strip()
    match = re.search(r'Account[:\s\\n]+.*?(\d{7})', text, re.I)
    if match:
        return match.group(1)
    return None

def _extract_patriot_waste_v3(text):
    """Patriot Waste - multiple formats"""
    if 'PATRIOT' not in text.upper():
        return None
    lines = text.split('\\n')
    for i, line in enumerate(lines):
        if 'CUSTOMER NO' in line.upper():
            for j in range(i+1, min(i+10, len(lines))):
                val = lines[j].strip()
                if re.match(r'^\d{6}$', val):
                    return val
    for i, line in enumerate(lines):
        if 'Account No' in line:
            for j in range(i, min(i+6, len(lines))):
                val = lines[j].strip()
                if re.match(r'^\d{6}$', val):
                    return val
    for i, line in enumerate(lines):
        if 'Account Number' in line:
            for j in range(i+1, min(i+5, len(lines))):
                val = lines[j].strip()
                if re.match(r'^\d{6}$', val):
                    return val
    return None

def _extract_granger_waste_v3(text):
    """Format: Account Number: 7-8 digit"""
    match = re.search(r'Account\s*Number:\s*(\d{7,8})', text)
    if match:
        return match.group(1)
    lines = text.split('\\n')
    for i, line in enumerate(lines):
        if 'Account Number' in line:
            for j in range(i+1, min(i+3, len(lines))):
                if re.match(r'^\d{7,8}$', lines[j].strip()):
                    return lines[j].strip()
    return None

def _extract_kimble_v3(text):
    """Format: Account Number followed by 6-digit"""
    lines = text.split('\\n')
    for i, line in enumerate(lines):
        if 'Account Number' in line:
            for j in range(i+1, min(i+8, len(lines))):
                val = lines[j].strip()
                if re.match(r'^\d{6}$', val):
                    return val
    return None

def _extract_apex_waste_v3(text):
    """Format: ACCOUNT # - 6-12 digit"""
    lines = text.split('\\n')
    for i, line in enumerate(lines):
        if 'ACCOUNT #' in line.upper():
            for j in range(i+1, min(i+8, len(lines))):
                val = lines[j].strip()
                if re.match(r'^\d{6,12}$', val):
                    return val
    return None

VENDOR_ACCOUNTS = {}

# ============================================================
# TIER 1: HIGH VOLUME VENDORS (>2,000 invoices)
# ============================================================

def _extract_waste_connections(text: str) -> Optional[str]:
    """Format: DDDD-XXXXXX or DDDD-XXXXXX-XXX (district-account or district-account-site)
    Examples: 3067-261791, 2013-3110648-002, 6061-2343883
    """
    match = re.search(r'(\d{4}-\d{5,9}(?:-\d{2,3})?)', text)
    return match.group(1) if match else None

VENDOR_ACCOUNTS['Waste Connections'] = {
    'has_account': True,
    'format': 'DDDD-XXXXXX[-XXX]',
    'examples': ['3067-261791', '2013-3110648-002', '6061-2343883'],
    'extract': _extract_waste_connections
}


def _extract_republic_services(text: str) -> Optional[str]:
    """Format: D-DDDD-DDDDDDD
    Examples: 3-0509-0312663, 3-0695-0027498
    """
    match = re.search(r'(\d-\d{4}-\d{7})', text)
    return match.group(1) if match else None

VENDOR_ACCOUNTS['Republic Services'] = {
    'has_account': True,
    'format': 'D-DDDD-DDDDDDD',
    'examples': ['3-0509-0312663', '3-0695-0027498', '3-0889-0061659'],
    'extract': _extract_republic_services
}


def _extract_waste_management(text: str) -> Optional[str]:
    """Format: WGY/WHM + alphanumeric (main) or NN-NNNNN-NNNNN (alternate)
    V3 FIX: Filter out misdetected vendors (WIN Waste, West Central, etc.)
    V4 FIX: Added WHM prefix for Waste Harmonics/NG invoices
    Examples: WGY17110UB, WGY04904RB, WHM15073NG, 18-40677-73005
    Note: 87.2% overall but 90.6% of actual WM - 93 are misdetected vendors
    """
    # Filter misdetected vendors (vendor detection issues, not extraction issues)
    misdetects = [
        'WIN WASTE', 'WEST CENTRAL', 'UNITED STATES DISPOSAL', "STEVE'S SANITATION",
        'HEARTLAND WM', 'BLUE COMPACTOR', 'WIN INNOVATIONS'
    ]
    if any(x in text.upper() for x in misdetects):
        return None

    # Format 1: WGY or WHM + alphanumeric (WHM for Waste Harmonics/NG accounts)
    match = re.search(r'(W(?:GY|HM)[A-Z0-9]{5,8})', text)
    if match:
        return match.group(1)
    
    # Format 2: Customer ID NN-NNNNN-NNNNN
    lines = text.split('\\n')
    for i, line in enumerate(lines):
        if 'Customer ID' in line:
            for j in range(i, min(i+3, len(lines))):
                match = re.search(r'\b(\d{2}-\d{5}-\d{5})\b', lines[j])
                if match:
                    return match.group(1)
    
    # Format 3: Westside variant Customer #: NN-NNNNN N
    match = re.search(r'Customer\s*#:\s*(\d{2}-\d{5}\s*\d?)', text)
    if match:
        return match.group(1).strip()
    
    return None

VENDOR_ACCOUNTS['Waste Management'] = {
    'has_account': True,
    'format': 'WGYXXXXXXXX or NN-NNNNN-NNNNN',
    'examples': ['WGY17110UB', 'WGY04904RB', '18-40677-73005'],
    'extract': _extract_waste_management
}


def _extract_gfl(text: str) -> Optional[str]:
    """Format: 2-letter prefix + digits or 9-digit numeric
    Variants: UK, AS, KW, KS, AW, U, P + digits
    Examples: UK829605, AS110323, 002294947
    """
    # Format 1: ACCOUNT NUMBER: NNNNNNNNN
    match = re.search(r'ACCOUNT\s*NUMBER:\s*(\d{9})', text, re.IGNORECASE)
    if match:
        return match.group(1)
    
    # Format 2: After CUSTOMER #: or ACCOUNT #:
    lines = text.split('\\n')
    for i, line in enumerate(lines):
        if 'CUSTOMER #' in line.upper() or 'ACCOUNT #' in line.upper():
            for j in range(i, min(i+6, len(lines))):
                match = re.search(r'\b([A-Z]{1,2}\d{4,8}|\d{9})\b', lines[j])
                if match:
                    return match.group(1)
    return None

VENDOR_ACCOUNTS['GFL'] = {
    'has_account': True,
    'format': 'XX######(#) or NNNNNNNNN',
    'examples': ['UK829605', 'AS110323', 'KW2256', '002294947'],
    'extract': _extract_gfl
}


def _extract_anytime_waste(text: str) -> Optional[str]:
    """Format: 5-digit numeric - multiple positions
    V3 FIX: Check line 0, ACCOUNT # header, and line 4
    Examples: 24234, 24479, 26944
    """
    lines = text.split('\\n')
    
    # Format 1: Line 0 is the account number (5-digit at start)
    if len(lines) > 0:
        val = lines[0].strip()
        if re.match(r'^\d{5}$', val):
            return val
    
    # Format 2: After ACCOUNT # header
    for i, line in enumerate(lines):
        if 'ACCOUNT #' in line.upper():
            for j in range(i+1, min(i+5, len(lines))):
                val = lines[j].strip()
                if re.match(r'^\d{5}$', val):
                    return val
    
    # Format 3: Line 4 position (original logic)
    if len(lines) > 4:
        val = lines[4].strip()
        if re.match(r'^\d{5}$', val):
            return val
    
    return None

VENDOR_ACCOUNTS['Anytime Waste'] = {
    'has_account': True,
    'format': 'NNNNN',
    'examples': ['24234', '24479', '26944'],
    'extract': _extract_anytime_waste
}


# ============================================================
# TIER 2: MEDIUM VOLUME VENDORS (1,000-2,000 invoices)
# ============================================================

def _extract_rumpke(text: str) -> Optional[str]:
    """Format: 10-digit numeric after Customer #:
    Examples: 4002536510, 4102892177
    """
    match = re.search(r'Customer\s*#:?\s*(?:\\n)?(?:Access\s*Code:?\s*\\n)?(\d{10})', text, re.IGNORECASE)
    return match.group(1) if match else None

VENDOR_ACCOUNTS['Rumpke'] = {
    'has_account': True,
    'format': 'NNNNNNNNNN',
    'examples': ['4002536510', '4102892177', '1202168117'],
    'extract': _extract_rumpke
}


def _extract_waste_pro(text: str) -> Optional[str]:
    """Format: 4-7 digit numeric
    Examples: 753008, 188369, 086355
    """
    if 'Recology' in text:
        return None
    lines = text.split('\\n')
    for i, line in enumerate(lines):
        if 'Account' in line:
            for j in range(i, min(i+20, len(lines))):
                val = lines[j].strip()
                match = re.match(r'^(\d{4,7})/\d+$', val)
                if match:
                    return match.group(1)
                if re.match(r'^(\d{4,7})$', val):
                    return val
    return None

VENDOR_ACCOUNTS['Waste Pro'] = {
    'has_account': True,
    'format': 'NNNNNN(N)',
    'examples': ['753008', '188369', '086355'],
    'extract': _extract_waste_pro
}


def _extract_cockey(text: str) -> Optional[str]:
    """Format: 5-digit or 5-3 digit format after ACCOUNT #
    Examples: 13010, 13010-007
    """
    lines = text.split('\\n')
    for i, line in enumerate(lines):
        if 'ACCOUNT #' in line.upper():
            for j in range(i, min(i+5, len(lines))):
                match = re.match(r'^(\d{5}(?:-\d{3})?)$', lines[j].strip())
                if match:
                    return match.group(1)
    return None

VENDOR_ACCOUNTS["Cockey's Enterprises"] = {
    'has_account': True,
    'format': 'NNNNN or NNNNN-NNN',
    'examples': ['13010', '13010-007', '13010-179'],
    'extract': _extract_cockey
}


def _extract_universal_waste(text: str) -> Optional[str]:
    """Format: 6-digit numeric
    V3 FIX: LWS format has account at line 2
    Examples: 273586, 274126, 261300
    """
    lines = text.split('\\n')
    
    # Format 1: LWS format - account at line 2
    if len(lines) > 2:
        val = lines[2].strip()
        if re.match(r'^\d{6}$', val):
            return val
    
    # Format 2: Customer Number: label
    for i, line in enumerate(lines):
        if 'Customer Number' in line:
            match = re.search(r'Customer\s*Number:\s*(\d{6})', line, re.I)
            if match:
                return match.group(1)
            for j in range(i+1, min(i+6, len(lines))):
                val = lines[j].strip()
                if re.match(r'^\d{6}$', val):
                    return val
    
    # Format 3: Line 7 fallback
    if len(lines) > 7:
        val = lines[7].strip()
        if re.match(r'^\d{5,6}$', val):
            return val
    
    return None

VENDOR_ACCOUNTS['Universal Waste'] = {
    'has_account': True,
    'format': 'NNNNNN',
    'examples': ['273586', '274126', '279858'],
    'extract': _extract_universal_waste
}


# ============================================================
# TIER 3: MEDIUM VOLUME VENDORS (500-1,000 invoices)
# ============================================================

def _extract_robinson_waste(text: str) -> Optional[str]:
    """Format: NNNNN.NNN, NNNNN-NNN, or simple 4-5 digit
    V3 FIX: Value appears BEFORE ACCOUNT NO. label in header
    V4 FIX: Added ACCOUNT NO. NNNN format for NG invoices
    Skip CUSTOMER ISSUE TICKETs (service tickets, not invoices)
    Examples: 55779.64, 55779.152, 2246, 1167
    """
    if 'CUSTOMER ISSUE TICKET' in text.upper():
        return None

    # Format 0: ACCOUNT NO. NNNN (NG invoice format)
    match = re.search(r'ACCOUNT\s*NO\.?\s*(\d{4,5})\b', text, re.I)
    if match:
        return match.group(1)

    lines = text.split('\n')

    # Format 1: NNNNN.NNN or NNNNN-NNN
    for line in lines[:25]:
        match = re.search(r'\b(\d{5}[\.\-]\d{1,3})\b', line)
        if match:
            return match.group(1)
    
    # Format 2: Find ACCOUNT NO. and look for 4-5 digit value nearby
    for i, line in enumerate(lines[:20]):
        if 'ACCOUNT NO' in line.upper():
            # Value is typically 2-6 lines BEFORE the label
            for j in range(max(0, i-6), i):
                val = lines[j].strip()
                if re.match(r'^\d{4,5}$', val):
                    return val
            # Also check after
            for j in range(i+1, min(i+5, len(lines))):
                val = lines[j].strip()
                if re.match(r'^\d{4,5}$', val):
                    return val
    
    return None

VENDOR_ACCOUNTS['Robinson Waste'] = {
    'has_account': True,
    'format': 'NNNNN.NNN',
    'examples': ['55779.64', '55779.152', '55779.107'],
    'extract': _extract_robinson_waste
}


def _extract_hamilton_alliance(text: str) -> Optional[str]:
    """Format: 4-digit numeric after ACCOUNT #
    Examples: 1042, 1102
    """
    lines = text.split('\\n')
    for i, line in enumerate(lines):
        if 'ACCOUNT #' in line.upper():
            for j in range(i, min(i+6, len(lines))):
                val = lines[j].strip()
                if re.match(r'^\d{4}$', val):
                    return val
    return None

VENDOR_ACCOUNTS['Hamilton Alliance'] = {
    'has_account': True,
    'format': 'NNNN',
    'examples': ['1042', '1102', '1027'],
    'extract': _extract_hamilton_alliance
}


def _extract_active_waste(text: str) -> Optional[str]:
    """Format: 5-digit numeric after ACCOUNT #
    Examples: 32650, 39109
    """
    lines = text.split('\\n')
    for i, line in enumerate(lines):
        if 'ACCOUNT #' in line.upper():
            for j in range(i, min(i+6, len(lines))):
                val = lines[j].strip()
                if re.match(r'^\d{5}$', val):
                    return val
    return None

VENDOR_ACCOUNTS['Active Waste'] = {
    'has_account': True,
    'format': 'NNNNN',
    'examples': ['32650', '39109', '48330'],
    'extract': _extract_active_waste
}


def _extract_priority_waste(text: str) -> Optional[str]:
    """Format: PW + 8 digits or ACC + 5 digits
    Examples: PW00011457, ACC27440
    """
    # Pattern 1: Account # with value (inline or next line)
    match = re.search(r'Account\s*#[\s:\n]*(PW\d{8}|ACC\d{5})', text, re.IGNORECASE)
    if match:
        return match.group(1)

    # Pattern 2: Columnar - Account # on one line, value on next
    lines = text.replace('\\n', '\n').split('\n')
    for i, line in enumerate(lines[:-1]):
        if re.match(r'Account\s*#\s*$', line, re.I):
            val = lines[i+1].strip()
            m = re.match(r'^(PW\d{8}|ACC\d{5})$', val, re.I)
            if m:
                return m.group(1)

    return None

VENDOR_ACCOUNTS['Priority Waste'] = {
    'has_account': True,
    'format': 'PWNNNNNNNN or ACCNNNNN',
    'examples': ['PW00011457', 'ACC27440', 'ACC28177'],
    'extract': _extract_priority_waste
}


def _extract_casella(text: str) -> Optional[str]:
    """Format: K/KI + digits, pure numeric, or NN-NNNNN N
    V3 FIX: Handle KI prefix, 10-digit numeric, skip price confirmations
    Examples: 81-39019 6, K100008742, KI00008742, 1100001394
    """
    if 'PRICE CONFIRMATION' in text.upper():
        return None
    
    lines = text.split('\\n')
    
    # Format 1: Customer Number with K/KI/KR prefix or pure numeric
    for i, line in enumerate(lines):
        if 'Customer Number' in line:
            for j in range(i+1, min(i+6, len(lines))):
                val = lines[j].strip()
                # K100008924, KI00008742
                if re.match(r'^K[IR]?\d{7,9}$', val, re.I):
                    return val.upper()
                # Pure numeric 1100001394 (10 digits)
                if re.match(r'^\d{10}$', val):
                    return val
    
    # Format 2: NN-NNNNN N (Cust#: or CUSTOMER NUMBER)
    for i, line in enumerate(lines):
        if 'Cust#:' in line or 'CUSTOMER NUMBER' in line.upper():
            for j in range(i, min(i+5, len(lines))):
                match = re.search(r'(\d{2}-\d{5}\s*\d)', lines[j])
                if match:
                    return match.group(1).strip()
    
    return None

VENDOR_ACCOUNTS['Casella'] = {
    'has_account': True,
    'format': 'NN-NNNNN N or KNNNNNNNNN',
    'examples': ['81-39019 6', '81-48863 6', 'K100008742'],
    'extract': _extract_casella
}


def _extract_boren_brothers(text: str) -> Optional[str]:
    """Format: 6-digit with leading zeros after CUSTOMER NO
    Examples: 005881, 006869
    """
    lines = text.split('\\n')
    for i, line in enumerate(lines):
        if 'CUSTOMER NO' in line.upper():
            for j in range(i, min(i+3, len(lines))):
                val = lines[j].strip()
                if re.match(r'^\d{6}$', val):
                    return val
    return None

VENDOR_ACCOUNTS['Boren Brothers'] = {
    'has_account': True,
    'format': 'NNNNNN',
    'examples': ['005881', '006869', '006132'],
    'extract': _extract_boren_brothers
}


def _extract_aspen_waste(text: str) -> Optional[str]:
    """Format: D-NNNNN N after Acct No.
    Examples: 4-82600 2, 4-83099 6
    """
    match = re.search(r'Acct\s*No\.?\s*(\d-\d{5}\s*\d?)', text, re.IGNORECASE)
    return match.group(1).strip() if match else None

VENDOR_ACCOUNTS['Aspen Waste'] = {
    'has_account': True,
    'format': 'N-NNNNN N',
    'examples': ['4-82600 2', '4-83099 6', '4-73859 5'],
    'extract': _extract_aspen_waste
}


# ============================================================
# TIER 4: LOWER VOLUME VENDORS (200-500 invoices)
# ============================================================

def _extract_meridian_waste(text: str) -> Optional[str]:
    """Format: NN-NNNNN(NN) N after Account No.
    Accepts 5-8 digits after hyphen
    Examples: 01-1276236 4, 70-0143542 2, 50-11702 3
    """
    # Pattern 1: Inline format
    match = re.search(r'Account\s*No\.?\s*(\d{2}-\d{5,8}\s*\d?)', text, re.IGNORECASE)
    if match:
        return match.group(1).strip()

    # Pattern 2: Columnar - Account No. on one line, value nearby
    lines = text.replace('\\n', '\n').split('\n')
    for i, line in enumerate(lines):
        if re.match(r'Account\s*No\.?\s*$', line, re.I):
            for j in range(i+1, min(i+6, len(lines))):
                val = lines[j].strip()
                m = re.match(r'^(\d{2}-\d{5,8}\s*\d?)$', val)
                if m:
                    return m.group(1).strip()

    return None

VENDOR_ACCOUNTS['Meridian Waste'] = {
    'has_account': True,
    'format': 'NN-NNNNN(NN) N',
    'examples': ['01-1276236 4', '50-11702 3'],
    'extract': _extract_meridian_waste
}


def _extract_frontier_waste(text: str) -> Optional[str]:
    """Format: 6-digit numeric after ACCOUNT #
    Examples: 207779, 274976
    """
    lines = text.split('\\n')
    for i, line in enumerate(lines):
        if 'ACCOUNT #' in line.upper():
            for j in range(i, min(i+6, len(lines))):
                val = lines[j].strip()
                if re.match(r'^\d{6}$', val):
                    return val
    return None

VENDOR_ACCOUNTS['Frontier Waste'] = {
    'has_account': True,
    'format': 'NNNNNN',
    'examples': ['207779', '274976', '190400'],
    'extract': _extract_frontier_waste
}


def _extract_fcc_environmental(text: str) -> Optional[str]:
    """Format: Multiple regional formats
    V3 FIX: Tampa TS format, Houston ACCOUNT #, PBC format, PSL format
    Examples: TS00154796, PBC-3453-5, 228252, PSL12345
    """
    lines = text.split('\\n')
    
    # Tampa TS format
    for i, line in enumerate(lines):
        if 'Customer ID:' in line:
            match = re.search(r'Customer\s*ID:\s*(TS\d{8})', line, re.I)
            if match:
                return match.group(1)
            for j in range(i+1, min(i+3, len(lines))):
                val = lines[j].strip()
                if re.match(r'^TS\d{8}$', val):
                    return val
    
    # PBC format - various: PBC-3453-5, PBC3453-10, etc.
    match = re.search(r'Customer\s*ID:\s*(PBC-?\d+-?\d+)', text, re.I)
    if match:
        return match.group(1)
    for i, line in enumerate(lines):
        if 'Customer ID:' in line:
            for j in range(i+1, min(i+3, len(lines))):
                val = lines[j].strip()
                if re.match(r'^PBC-?\d+-?\d+$', val):
                    return val
    
    # PSL format
    for i, line in enumerate(lines):
        if 'Customer ID:' in line:
            for j in range(i, min(i+10, len(lines))):
                val = lines[j].strip()
                if re.match(r'^PSL\d{4,6}$', val):
                    return val
    
    # Houston format: ACCOUNT # header with 5-6 digit value
    for i, line in enumerate(lines):
        if 'ACCOUNT #' in line.upper():
            for j in range(i+1, min(i+6, len(lines))):
                val = lines[j].strip()
                if re.match(r'^\d{5,6}$', val):
                    return val
    
    return None

VENDOR_ACCOUNTS['FCC Environmental'] = {
    'has_account': True,
    'format': 'TSNNNNNNNN or PBC-NNNN-N or NNNNNN',
    'examples': ['TS00154796', 'PBC-3453-5', '270894'],
    'extract': _extract_fcc_environmental
}


def _extract_smarttrash(text: str) -> Optional[str]:
    """Format: C + 5 digits after Customer
    Examples: C02096, C02010
    """
    match = re.search(r'Customer\s+(C\d{5})', text, re.IGNORECASE)
    return match.group(1) if match else None

VENDOR_ACCOUNTS['SmartTrash'] = {
    'has_account': True,
    'format': 'CNNNNN',
    'examples': ['C02096', 'C02010', 'C01779'],
    'extract': _extract_smarttrash
}


def _extract_lrs(text: str) -> Optional[str]:
    """Format: NNNNN.NN or NNNNNN (4-6 digits with optional decimal)
    Examples: 12949.1, 702806
    """
    lines = text.split('\\n')
    for i, line in enumerate(lines):
        if 'Customer No' in line:
            for j in range(i, min(i+8, len(lines))):
                val = lines[j].strip()
                if re.match(r'^\d{4,6}(\.\d{1,2})?$', val):
                    return val
    return None

VENDOR_ACCOUNTS['LRS'] = {
    'has_account': True,
    'format': 'NNNNN.NN or NNNNNN',
    'examples': ['12949.1', '702806', '7995.11'],
    'extract': _extract_lrs
}


def _extract_121_disposal(text: str) -> Optional[str]:
    """Format: 8-digit starting with 121
    Examples: 12115904, 12116430
    """
    match = re.search(r'(?:Account\s*#|CUSTOMER\s*NO)\s*\\n(\d{8})', text, re.IGNORECASE)
    if match and match.group(1).startswith('121'):
        return match.group(1)
    match = re.search(r'\b(121\d{5})\b', text)
    if match:
        return match.group(1)
    match = re.search(r'121DISPOSAL(\d{6})', text, re.IGNORECASE)
    if match:
        return '121' + match.group(1)[:5]
    return None

VENDOR_ACCOUNTS['121 Disposal'] = {
    'has_account': True,
    'format': '121NNNNN',
    'examples': ['12115904', '12116430', '12115951'],
    'extract': _extract_121_disposal
}


def _extract_best_cleaner(text: str) -> Optional[str]:
    """Format: 12-digit numeric ID
    Examples: 621620359356, 621620365863
    """
    match = re.search(r'ID#:?\s*(\d{12})', text)
    if match:
        return match.group(1)
    lines = text.split('\\n')
    if len(lines) > 3:
        val = lines[3].strip()
        if re.match(r'^\d{12}$', val):
            return val
    return None

VENDOR_ACCOUNTS['Best Cleaner'] = {
    'has_account': True,
    'format': 'NNNNNNNNNNNN',
    'examples': ['621620359356', '621620365863'],
    'extract': _extract_best_cleaner
}


def _extract_fusion_waste(text: str) -> Optional[str]:
    """Format: 4-8 digit numeric after CUSTOMER NO
    Examples: 001211, 004402
    """
    lines = text.split('\\n')
    for i, line in enumerate(lines):
        if 'CUSTOMER NO' in line.upper() and 'PO' not in line.upper():
            if i+1 < len(lines):
                val = lines[i+1].strip()
                if re.match(r'^\d{4,8}$', val):
                    return val
    return None

VENDOR_ACCOUNTS['Fusion Waste'] = {
    'has_account': True,
    'format': 'NNNNNN',
    'examples': ['001211', '004402', '004388'],
    'extract': _extract_fusion_waste
}


def _extract_coastal_waste(text: str) -> Optional[str]:
    """Format: Multiple formats for 4-6 digit numeric
    V3 FIX: Handle "CUSTOMER NO." header with value on next line
    Examples: 2584, 13555, 41259
    """
    lines = text.split('\\n')
    
    # Format 1: "Customer No.: 2584" inline
    match = re.search(r'Customer\s*No\.?:?\s*(\d{4,6})', text, re.I)
    if match:
        return match.group(1)
    
    # Format 2: "CUSTOMER NO." header with value on next line
    for i, line in enumerate(lines):
        if re.search(r'CUSTOMER\s*NO\.?', line, re.I):
            for j in range(i+1, min(i+4, len(lines))):
                val = lines[j].strip()
                if re.match(r'^\d{4,6}$', val):
                    return val
    
    # Format 3: "Customer" standalone header, value several lines later
    for i, line in enumerate(lines):
        if line.strip() == 'Customer':
            for j in range(i+1, min(i+10, len(lines))):
                val = lines[j].strip()
                if re.match(r'^\d{4,6}$', val):
                    return val
    
    return None

VENDOR_ACCOUNTS['Coastal Waste'] = {
    'has_account': True,
    'format': 'NNNNN',
    'examples': ['2584', '13555', '10978'],
    'extract': _extract_coastal_waste
}


def _extract_flood_brothers(text: str) -> Optional[str]:
    """Format: 5-8 digit numeric after CUSTOMER NO
    Examples: 0228056, 0233475
    """
    lines = text.split('\\n')
    for i, line in enumerate(lines):
        if 'CUSTOMER NO' in line.upper():
            for j in range(i, min(i+5, len(lines))):
                match = re.search(r'\b(\d{5,8})\b', lines[j])
                if match:
                    return match.group(1)
    return None

VENDOR_ACCOUNTS['Flood Brothers'] = {
    'has_account': True,
    'format': 'NNNNNNN',
    'examples': ['0228056', '0233475', '0201010'],
    'extract': _extract_flood_brothers
}


def _extract_alaska_waste(text: str) -> Optional[str]:
    """Format: Waste Connections subsidiary - DDDD-NNNNNN[-NNN]
    Examples: 2430-736709, 2436-736659
    """
    match = re.search(r'(\d{4}-\d{5,9}(?:-\d{2,3})?)', text)
    return match.group(1) if match else None

VENDOR_ACCOUNTS['Alaska Waste'] = {
    'has_account': True,
    'format': 'DDDD-NNNNNN',
    'examples': ['2430-736709', '2436-736659'],
    'extract': _extract_alaska_waste
}


def _extract_eagle_disposal(text: str) -> Optional[str]:
    """Format: 12-digit numeric ID
    Examples: 638730778561, 638730786593
    """
    match = re.search(r'ID#:?\s*(\d{12})', text)
    if match:
        return match.group(1)
    lines = text.split('\\n')
    if len(lines) > 3:
        val = lines[3].strip()
        if re.match(r'^\d{12}$', val):
            return val
    return None

VENDOR_ACCOUNTS['Eagle Disposal'] = {
    'has_account': True,
    'format': 'NNNNNNNNNNNN',
    'examples': ['638730778561', '638730786593'],
    'extract': _extract_eagle_disposal
}


def _extract_papillion_sanitation(text: str) -> Optional[str]:
    """Format: Waste Connections subsidiary - DDDD-NNNNNNNN[-NNN]
    Examples: 3050-30202479-001, 3050-30240333-002
    """
    match = re.search(r'(\d{4}-\d{5,9}(?:-\d{2,3})?)', text)
    return match.group(1) if match else None

VENDOR_ACCOUNTS['Papillion Sanitation'] = {
    'has_account': True,
    'format': 'DDDD-NNNNNNNN',
    'examples': ['3050-30202479-001', '3050-30240333-002'],
    'extract': _extract_papillion_sanitation
}


def _extract_murreys_disposal(text: str) -> Optional[str]:
    """Format: Waste Connections subsidiary - DDDD-NNNNNNNNN[-NNN]
    Examples: 2111-321905531, 2112-241446-003
    """
    match = re.search(r'(\d{4}-\d{5,9}(?:-\d{2,3})?)', text)
    return match.group(1) if match else None

VENDOR_ACCOUNTS['Murreys Disposal'] = {
    'has_account': True,
    'format': 'DDDD-NNNNNNNNN',
    'examples': ['2111-321905531', '2112-241446-003'],
    'extract': _extract_murreys_disposal
}


def _extract_lawrence_waste(text: str) -> Optional[str]:
    """Format: 4-8 digit numeric after CUSTOMER NO
    Examples: 9450
    """
    lines = text.split('\\n')
    for i, line in enumerate(lines):
        if 'CUSTOMER NO' in line.upper():
            for j in range(i+1, min(i+5, len(lines))):
                val = lines[j].strip()
                if re.match(r'^\d{4,8}$', val):
                    return val
    return None

VENDOR_ACCOUNTS['Lawrence Waste'] = {
    'has_account': True,
    'format': 'NNNN',
    'examples': ['9450'],
    'extract': _extract_lawrence_waste
}


def _extract_capital_waste(text: str) -> Optional[str]:
    """Format: 4-8 digit numeric after ACCOUNT label
    Examples: 162588, 2674727
    """
    lines = text.split('\\n')
    for i, line in enumerate(lines):
        if line.strip().upper() == 'ACCOUNT':
            for j in range(i+1, min(i+5, len(lines))):
                val = lines[j].strip()
                if re.match(r'^\d{4,8}$', val):
                    return val
    return None

VENDOR_ACCOUNTS['Capital Waste'] = {
    'has_account': True,
    'format': 'NNNNNN',
    'examples': ['162588', '2674727', '2719586'],
    'extract': _extract_capital_waste
}


def _extract_american_disposal(text: str) -> Optional[str]:
    """Format: WC subsidiary format or 4-8 digit numeric
    Examples: 6319-615996, 7721
    """
    match = re.search(r'(\d{4}-\d{5,9})', text)
    if match:
        return match.group(1)
    lines = text.split('\\n')
    for i, line in enumerate(lines):
        if 'ACCOUNT NUMBER' in line.upper():
            for j in range(i+1, min(i+4, len(lines))):
                val = lines[j].strip()
                if re.match(r'^\d{4,8}$', val):
                    return val
    return None

VENDOR_ACCOUNTS['American Disposal'] = {
    'has_account': True,
    'format': 'DDDD-NNNNNN or NNNN',
    'examples': ['6319-615996', '7721', '7640'],
    'extract': _extract_american_disposal
}


def _extract_burrtec(text: str) -> Optional[str]:
    """Format: Numeric (6-10 digit) or alphanumeric (NN-XX NNNNNN)
    Examples: 15063480, 136725585, 47-TD 600084
    """
    lines = text.replace('\\n', '\n').split('\n')

    # Pattern 1: Account Number header with alphanumeric format (NN-XX NNNNNN)
    for i, line in enumerate(lines):
        if 'account number' in line.lower():
            for j in range(i+1, min(i+5, len(lines))):
                val = lines[j].strip()
                m = re.match(r'^(\d{2}-[A-Z]{2}\s*\d{6})$', val)
                if m:
                    return m.group(1)
                if re.match(r'^\d{6,10}$', val):
                    return val

    # Pattern 2: Customer Number with numeric format
    for i, line in enumerate(lines):
        if 'customer number' in line.lower():
            for j in range(i+1, min(i+5, len(lines))):
                val = lines[j].strip()
                if re.match(r'^\d{6,10}$', val):
                    return val

    return None

VENDOR_ACCOUNTS['Burrtec'] = {
    'has_account': True,
    'format': 'NNNNNNNNN or NN-XX NNNNNN',
    'examples': ['15063480', '47-TD 600084'],
    'extract': _extract_burrtec
}


def _extract_friedman_recycling(text: str) -> Optional[str]:
    """Format: 8-digit numeric on line 5
    Examples: 11755100, 11750900
    """
    lines = text.split('\\n')
    if len(lines) > 5:
        val = lines[5].strip()
        if re.match(r'^\d{8}$', val):
            return val
    return None

VENDOR_ACCOUNTS['Friedman Recycling'] = {
    'has_account': True,
    'format': 'NNNNNNNN',
    'examples': ['11755100', '11750900'],
    'extract': _extract_friedman_recycling
}


def _extract_navajo_sanitation(text: str) -> Optional[str]:
    """Format: 12-digit numeric ID
    Examples: 577170044245, 577170042934
    """
    match = re.search(r'ID#:\s*(\d{12})', text)
    if match:
        return match.group(1)
    lines = text.split('\\n')
    if len(lines) > 3:
        val = lines[3].strip()
        if re.match(r'^\d{12}$', val):
            return val
    return None

VENDOR_ACCOUNTS['Navajo Sanitation'] = {
    'has_account': True,
    'format': 'NNNNNNNNNNNN',
    'examples': ['577170044245', '577170042934'],
    'extract': _extract_navajo_sanitation
}


def _extract_novak_sanitary(text: str) -> Optional[str]:
    """Format: Waste Connections subsidiary - DDDD-NNNNNN
    Examples: 3031-130008, 3031-130965
    """
    match = re.search(r'(\d{4}-\d{5,9})', text)
    return match.group(1) if match else None

VENDOR_ACCOUNTS['Novak Sanitary'] = {
    'has_account': True,
    'format': 'DDDD-NNNNNN',
    'examples': ['3031-130008', '3031-130965'],
    'extract': _extract_novak_sanitary
}


def _extract_win_waste(text: str) -> Optional[str]:
    """Format: NN-NNNNN-NNNN
    Examples: 30-32676-0009, 28-13467-0050
    """
    match = re.search(r'CUSTOMER\s*NO\.?\s*(\d{2}-\d{5}-\d{4})', text, re.I)
    if match:
        return match.group(1)
    lines = text.split('\\n')
    for i, line in enumerate(lines):
        if 'CUSTOMER NO' in line.upper():
            if i+1 < len(lines):
                val = lines[i+1].strip()
                if re.match(r'^\d{2}-\d{5}-\d{4}$', val):
                    return val
    return None

VENDOR_ACCOUNTS['Win Waste'] = {
    'has_account': True,
    'format': 'NN-NNNNN-NNNN',
    'examples': ['30-32676-0009', '28-13467-0050'],
    'extract': _extract_win_waste
}


def _extract_best_way_disposal(text: str) -> Optional[str]:
    """Format: 9-digit numeric or I-NNNNNN format
    Examples: 157708100, 171954800, I-202541
    """
    # Pattern 1: 9-digit inline
    match = re.search(r'Account\s*Number:?\s*(\d{9})', text, re.I)
    if match:
        return match.group(1)

    # Pattern 2: I-NNNNNN format (letter prefix)
    match = re.search(r'Account\s*Number[\s\n]*[^\n]*[\s\n]*(I-\d{6})', text, re.I)
    if match:
        return match.group(1)

    # Pattern 3: Columnar - Account Number on one line, value on next
    lines = text.replace('\\n', '\n').split('\n')
    for i, line in enumerate(lines[:-1]):
        if 'account number' in line.lower():
            for j in range(i+1, min(i+4, len(lines))):
                val = lines[j].strip()
                if re.match(r'^\d{9}$', val):
                    return val
                m = re.match(r'^(I-\d{6})$', val)
                if m:
                    return m.group(1)

    return None

VENDOR_ACCOUNTS['Best Way Disposal'] = {
    'has_account': True,
    'format': 'NNNNNNNNN or I-NNNNNN',
    'examples': ['157708100', 'I-202541'],
    'extract': _extract_best_way_disposal
}


def _extract_athens_services(text: str) -> Optional[str]:
    """Format: Alphanumeric (2M, CE, TC, 1M, ES prefixes)
    V4 FIX: Added XX-NNN format for NG invoices (ES-744)
    Examples: 2M0010827, CE0019867, 1M0011195, ES0000720, ES-744
    """
    # Format 0: ACCOUNT XX-NNN (NG invoice format)
    match = re.search(r'ACCOUNT\s+([A-Z]{2}-\d{3,4})\b', text, re.I)
    if match:
        return match.group(1)

    lines = text.replace('\\n', '\n').split('\n')

    for i, line in enumerate(lines):
        if 'ACCOUNT' in line.upper():
            for j in range(i, min(i+5, len(lines))):
                if 'NUMBER' in lines[j].upper() or j > i:
                    for k in range(j, min(j+4, len(lines))):
                        val = lines[k].strip()
                        # Match alphanumeric: letter+digit or digit+letter prefix
                        # 2M0010827, CE0019867, 1M0011195, ES0000720
                        if re.match(r'^[A-Z0-9]{2}\d{7}$', val):
                            return val
    return None

VENDOR_ACCOUNTS['Athens Services'] = {
    'has_account': True,
    'format': 'XXNNNNNNN',
    'examples': ['2M0010827', 'CE0019867', '1M0011195'],
    'extract': _extract_athens_services
}


def _extract_compactor_rentals(text: str) -> Optional[str]:
    """Format: 4-6 digit numeric Customer ID
    Examples: 2158, 30109
    """
    match = re.search(r'Customer:\s*(\d{4,6})', text, re.I)
    return match.group(1) if match else None

VENDOR_ACCOUNTS['Compactor Rentals of America'] = {
    'has_account': True,
    'format': 'NNNN',
    'examples': ['2158', '30109', '1099'],
    'extract': _extract_compactor_rentals
}


def _extract_homewood_disposal(text: str) -> Optional[str]:
    """Format: NN-NNNNNN N
    Examples: 20-284298 5, 20-284308 2
    """
    lines = text.split('\\n')
    for i, line in enumerate(lines):
        if 'Customer #' in line:
            if i+1 < len(lines):
                val = lines[i+1].strip()
                if re.match(r'^\d{2}-\d{6}\s*\d?$', val):
                    return val
    return None

VENDOR_ACCOUNTS['Homewood Disposal'] = {
    'has_account': True,
    'format': 'NN-NNNNNN N',
    'examples': ['20-284298 5', '20-284308 2'],
    'extract': _extract_homewood_disposal
}


def _extract_crr(text: str) -> Optional[str]:
    """Format: 9-digit numeric with optional letter prefix
    Examples: 000463579, 000162329
    """
    lines = text.split('\\n')
    for i, line in enumerate(lines):
        if 'Account Number' in line:
            for j in range(i+1, min(i+5, len(lines))):
                val = lines[j].strip()
                if re.match(r'^[A-Z]?\d{5,10}$', val):
                    return val
    return None

VENDOR_ACCOUNTS['CR&R'] = {
    'has_account': True,
    'format': 'NNNNNNNNN',
    'examples': ['000463579', '000162329'],
    'extract': _extract_crr
}


def _extract_kimble(text: str) -> Optional[str]:
    """Format: 5-10 digit numeric after CUSTOMER NO
    Examples: 242875, 552821
    """
    lines = text.split('\\n')
    for i, line in enumerate(lines):
        if 'CUSTOMER NO' in line.upper():
            for j in range(i+1, min(i+5, len(lines))):
                val = lines[j].strip()
                if re.match(r'^\d{5,10}$', val):
                    return val
    return None

VENDOR_ACCOUNTS['Kimble'] = {
    'has_account': True,
    'format': 'NNNNNN',
    'examples': ['242875', '552821'],
    'extract': _extract_kimble_v3
}


# ============================================================
# NEW VENDORS - DECEMBER 2024 ANALYSIS
# ============================================================

def _extract_ware_disposal(text: str) -> Optional[str]:
    """Format: NN-NNNNNN N (Account #)
    Examples: 01-139609, 01-302116, 01-19432 3
    """
    match = re.search(r'Account\s*#[:\s]*(\d{2}-\d{5,6}\s*\d?)', text, re.I)
    if match:
        return match.group(1).strip()
    # Look in footer section too
    lines = text.split('\\n')
    for line in lines:
        if 'Account #:' in line:
            match = re.search(r'(\d{2}-\d{5,6}\s*\d?)', line)
            if match:
                return match.group(1).strip()
    return None

VENDOR_ACCOUNTS['Ware Disposal'] = {
    'has_account': True,
    'format': 'NN-NNNNNN N',
    'examples': ['01-139609', '01-302116', '01-19432 3'],
    'extract': _extract_ware_disposal
}


def _extract_tower_compactor(text: str) -> Optional[str]:
    """Format: Alphanumeric Customer ID (e.g., UPS012, QED001, HAMO03)
    Must be 2-4 letters + 2-3 digits pattern
    Examples: UPS012, QED001, UPS005, HON003, HAMO03
    V10 FIX: Handle multiple header formats
    """
    # Normalize text
    normalized = text.replace('\\n', '\n')
    lines = normalized.split('\n')

    for i, line in enumerate(lines):
        if 'Customer ID' in line:
            # Check next line for alphanumeric ID
            if i + 1 < len(lines):
                val = lines[i + 1].strip()
                # Match 2-4 letters followed by 2-3 digits
                if re.match(r'^[A-Z]{2,4}\d{2,3}$', val, re.I):
                    return val.upper()
    return None

VENDOR_ACCOUNTS['Tower Compactor'] = {
    'has_account': True,
    'format': 'XXXNNN',
    'examples': ['UPS012', 'QED001', 'UPS005'],
    'extract': _extract_tower_compactor
}


def _extract_national_equipment_solutions(text: str) -> Optional[str]:
    """Format: 3-4 digit numeric Account Number
    Examples: 4296, 4301, 698
    """
    match = re.search(r'Account\s*Number\s*\\n(\d{3,4})', text, re.I)
    if match:
        return match.group(1)
    return None

VENDOR_ACCOUNTS['National Equipment Solutions'] = {
    'has_account': True,
    'format': 'NNN(N)',
    'examples': ['4296', '4301', '698'],
    'extract': _extract_national_equipment_solutions
}


def _extract_panzarella_waste(text: str) -> Optional[str]:
    """Format: NN-NNNN N (Account No.)
    Examples: 01-4656 4
    """
    match = re.search(r'Account\s*No\.?\s*(\d{2}-\d{4}\s*\d?)', text, re.I)
    if match:
        return match.group(1).strip()
    return None

VENDOR_ACCOUNTS['Panzarella Waste'] = {
    'has_account': True,
    'format': 'NN-NNNN N',
    'examples': ['01-4656 4'],
    'extract': _extract_panzarella_waste
}


def _extract_county_hauling(text: str) -> Optional[str]:
    """Format: Two sub-vendors + filter misdetected WM
    V3 FIX: 
    1. Noble Environmental (PA): Headers then values pattern, account 5 lines after "ACCOUNT NO."
    2. Lake County Hauling (WC subsidiary): DDDD-NNNNNN format
    3. Filter misdetected Waste Management invoices
    Examples: 166165, 1052-123456
    """
    # Filter misdetected WM
    if 'WASTE MANAGEMENT' in text.upper() or 'WGY' in text.upper() or 'wm.com' in text.lower():
        return None
    
    lines = text.split('\\n')
    
    # Format 1: Lake County Hauling (Waste Connections)
    match = re.search(r'(\d{4}-\d{5,6})', text)
    if match and 'LAKE COUNTY' in text.upper():
        return match.group(1)
    
    # Format 2: Noble Environmental - header/value pattern
    # Headers: INVOICE NO. | PAGE | DATE | ACCOUNT NO. | REFERENCE NO.
    # Values appear 5 lines after each header
    for i, line in enumerate(lines):
        if line.strip() == 'ACCOUNT NO.':
            # Account value is 5 lines after header
            if i + 5 < len(lines):
                val = lines[i + 5].strip()
                if re.match(r'^\d{5,6}$', val):
                    return val
    
    # Fallback: original pattern
    match = re.search(r'ACCOUNT\s*NO\.?\s*\\n(\d{6})', text, re.I)
    if match:
        return match.group(1)
    
    return None

VENDOR_ACCOUNTS['County Hauling'] = {
    'has_account': True,
    'format': 'NNNNNN',
    'examples': ['166165'],
    'extract': _extract_county_hauling
}


def _extract_lightning_disposal(text: str) -> Optional[str]:
    """Format: 5-digit numeric
    V3 FIX: Number appears BEFORE label in OCR (32027\\nCUSTOMER NO.)
    Examples: 32027, 29100
    """
    lines = text.split('\\n')
    
    # Pattern 1: Check lines before and after CUSTOMER NO.
    for i, line in enumerate(lines):
        if 'CUSTOMER NO' in line.upper():
            # Check previous lines
            for j in range(max(0, i-3), i):
                val = lines[j].strip()
                if re.match(r'^\d{5}$', val):
                    return val
            # Check next lines
            for j in range(i+1, min(i+4, len(lines))):
                val = lines[j].strip()
                if re.match(r'^\d{5}$', val):
                    return val
    
    # Pattern 2: Look for standalone 5-digit in header area with LIGHTNING context
    for i, line in enumerate(lines[:25]):
        val = line.strip()
        if re.match(r'^\d{5}$', val):
            context = ' '.join(lines[max(0,i-8):min(len(lines),i+8)])
            if 'LIGHTNING' in context.upper():
                return val
    
    return None

VENDOR_ACCOUNTS['Lightning Disposal'] = {
    'has_account': True,
    'format': 'NNNNN',
    'examples': ['32027'],
    'extract': _extract_lightning_disposal
}


def _extract_renewable_resources(text: str) -> Optional[str]:
    """Format: NN-NNNNN N (Customer Number)
    Examples: 01-26311 0
    """
    match = re.search(r'Customer\s*Number\s*(\d{2}-\d{5}\s*\d?)', text, re.I)
    if match:
        return match.group(1).strip()
    return None

VENDOR_ACCOUNTS['Renewable Resources'] = {
    'has_account': True,
    'format': 'NN-NNNNN N',
    'examples': ['01-26311 0'],
    'extract': _extract_renewable_resources
}


def _extract_atlas_disposal(text: str) -> Optional[str]:
    """Format: NN-NNNNNNN (e.g., 01-0202488)
    V3 FIX: Handle both "Account #:" and "Account #." (colon or period)
    Examples: 01-0202488, 01-0209302
    """
    # Match both : and . after Account #
    match = re.search(r'Account\s*#[\.:]\s*(\d{2}-\d{7})', text, re.I)
    if match:
        return match.group(1)
    
    lines = text.split('\\n')
    for i, line in enumerate(lines):
        if re.search(r'Account\s*#[\.\:]', line, re.I):
            for j in range(i+1, min(i+5, len(lines))):
                val = lines[j].strip()
                if re.match(r'^\d{2}-\d{7}$', val):
                    return val
    return None

VENDOR_ACCOUNTS['Atlas Disposal'] = {
    'has_account': True,
    'format': 'NN-NNNNNNN',
    'examples': ['01-0202488', '01-0209302'],
    'extract': _extract_atlas_disposal
}


def _extract_stevens_disposal(text: str) -> Optional[str]:
    """Format: Alphanumeric Account # (e.g., CMA7438)
    Examples: CMA7438, CMA7447
    """
    match = re.search(r'Account\s*#\s*\\n([A-Z0-9]+)', text, re.I)
    if match:
        return match.group(1)
    # Alternative location
    match = re.search(r'ACCOUNT\s*NUMBER\s*\\n([A-Z0-9]+)', text, re.I)
    if match:
        return match.group(1)
    return None

VENDOR_ACCOUNTS['Stevens Disposal'] = {
    'has_account': True,
    'format': 'XXNNNNN',
    'examples': ['CMA7438', 'CMA7447'],
    'extract': _extract_stevens_disposal
}


def _extract_usa_waste(text: str) -> Optional[str]:
    """Format: 6-digit numeric ACCOUNT #
    Examples: 226822
    """
    match = re.search(r'ACCOUNT\s*#\s*(\d{6})', text, re.I)
    if match:
        return match.group(1)
    return None

VENDOR_ACCOUNTS['USA Waste'] = {
    'has_account': True,
    'format': 'NNNNNN',
    'examples': ['226822'],
    'extract': _extract_usa_waste
}


def _extract_all_american_waste(text: str) -> Optional[str]:
    """Format: 6-digit numeric ACCOUNT #
    Examples: 226822, 207498
    """
    match = re.search(r'ACCOUNT\s*#\s*(\d{6})', text, re.I)
    if match:
        return match.group(1)
    return None

VENDOR_ACCOUNTS['All American Waste'] = {
    'has_account': True,
    'format': 'NNNNNN',
    'examples': ['226822', '207498'],
    'extract': _extract_all_american_waste
}


def _extract_nexus_disposal(text: str) -> Optional[str]:
    """Format: NNNNN-NNN (ACCOUNT:)
    Examples: 23736-018, 23736-019
    """
    match = re.search(r'ACCOUNT:\s*(\d{5}-\d{3})', text, re.I)
    if match:
        return match.group(1)
    return None

VENDOR_ACCOUNTS['Nexus Disposal'] = {
    'has_account': True,
    'format': 'NNNNN-NNN',
    'examples': ['23736-018', '23736-019'],
    'extract': _extract_nexus_disposal
}


def _extract_knighthorst(text: str) -> Optional[str]:
    """Format: 4-5 digit numeric Account
    Examples: 30016, 5194
    """
    match = re.search(r'Account\s*\\n(\d{4,5})', text, re.I)
    if match:
        return match.group(1)
    return None

VENDOR_ACCOUNTS['KnightHorst'] = {
    'has_account': True,
    'format': 'NNNNN',
    'examples': ['30016', '5194'],
    'extract': _extract_knighthorst
}


def _extract_all_waste(text: str) -> Optional[str]:
    """Format: N-NNNNNN N (e.g., 1-248930 7, 3-84623 3)
    V3 FIX: Also handle Cust # pattern and search nearby lines
    Examples: 1-248930 7, 3-84623 3
    """
    # Direct patterns
    match = re.search(r'Account\s*#:\s*(\d-\d{5,6}\s*\d)', text, re.I)
    if match:
        return match.group(1).strip()
    
    match = re.search(r'Cust\s*#\s*(\d-\d{5,6}\s*\d)', text, re.I)
    if match:
        return match.group(1).strip()
    
    # Search near keywords
    lines = text.split('\\n')
    for i, line in enumerate(lines):
        if 'Account' in line or 'Cust' in line:
            for j in range(i, min(i+5, len(lines))):
                match = re.search(r'(\d-\d{5,6}\s*\d)', lines[j])
                if match:
                    return match.group(1).strip()
    return None

VENDOR_ACCOUNTS['All Waste'] = {
    'has_account': True,
    'format': 'N-NNNNNN N',
    'examples': ['1-248930 7', '3-84623 3'],
    'extract': _extract_all_waste
}


def _extract_arrowaste(text: str) -> Optional[str]:
    """Format: NN-NNNNN N (Cust. #)
    Examples: 91-53681 3, 91-201356 3
    """
    match = re.search(r'Cust\.\s*#\s*\\n(\d{2}-\d{5}\s*\d)', text, re.I)
    if match:
        return match.group(1).strip()
    return None

VENDOR_ACCOUNTS['Arrowaste'] = {
    'has_account': True,
    'format': 'NN-NNNNN N',
    'examples': ['91-53681 3', '91-201356 3'],
    'extract': _extract_arrowaste
}


def _extract_ace_recycling(text: str) -> Optional[str]:
    """Format: 6-digit numeric ACCOUNT #
    Examples: 802026, 804589
    """
    match = re.search(r'ACCOUNT\s*#\s*\\n(\d{6})', text, re.I)
    if match:
        return match.group(1)
    return None

VENDOR_ACCOUNTS['Ace Recycling'] = {
    'has_account': True,
    'format': 'NNNNNN',
    'examples': ['802026', '804589'],
    'extract': _extract_ace_recycling_v3
}


def _extract_texas_disposal(text: str) -> Optional[str]:
    """Format: N-NNNNNN (Customer Number)
    Examples: 1-259930
    """
    match = re.search(r'Customer\s*Number\s*\\n(\d-\d{6})', text, re.I)
    if match:
        return match.group(1)
    return None

VENDOR_ACCOUNTS['Texas Disposal'] = {
    'has_account': True,
    'format': 'N-NNNNNN',
    'examples': ['1-259930'],
    'extract': _extract_texas_disposal_v3
}


def _extract_disposal_management(text: str) -> Optional[str]:
    """Format: 6-digit numeric ACCOUNT#
    Examples: 257240, 257215
    """
    match = re.search(r'ACCOUNT#\s*\\n(\d{6})', text, re.I)
    if match:
        return match.group(1)
    return None

VENDOR_ACCOUNTS['Disposal Management'] = {
    'has_account': True,
    'format': 'NNNNNN',
    'examples': ['257240', '257215'],
    'extract': _extract_disposal_management
}


def _extract_live_oak(text: str) -> Optional[str]:
    """Format: 6-digit numeric CUSTOMER NO or Acct#
    Examples: 170369, 173487
    """
    match = re.search(r'(?:CUSTOMER\s*NO|Acct#)\s*\\n?(\d{6})', text, re.I)
    if match:
        return match.group(1)
    return None

VENDOR_ACCOUNTS['Live Oak'] = {
    'has_account': True,
    'format': 'NNNNNN',
    'examples': ['170369', '173487'],
    'extract': _extract_live_oak
}


def _extract_ankeny_sanitation(text: str) -> Optional[str]:
    """Format: NN-NNNNNNN (Customer #)
    Examples: 01-1592756, 01-1482149
    """
    match = re.search(r'Customer\s*#:\s*(\d{2}-\d{7})', text, re.I)
    if match:
        return match.group(1)
    return None

VENDOR_ACCOUNTS['Ankeny Sanitation'] = {
    'has_account': True,
    'format': 'NN-NNNNNNN',
    'examples': ['01-1592756', '01-1482149'],
    'extract': _extract_ankeny_sanitation_v3
}


def _extract_granger_waste(text: str) -> Optional[str]:
    """Format: 7-8 digit numeric Account Number
    Examples: 2996640, 18774340
    """
    match = re.search(r'Account\s*Number:\s*(\d{7,8})', text, re.I)
    if match:
        return match.group(1)
    return None

VENDOR_ACCOUNTS['Granger Waste'] = {
    'has_account': True,
    'format': 'NNNNNNN(N)',
    'examples': ['2996640', '18774340'],
    'extract': _extract_granger_waste_v3
}


def _extract_stericycle(text: str) -> Optional[str]:
    """Format: 10-digit numeric Customer No. (Payer)
    Examples: 3001288443, 3001313731
    """
    match = re.search(r'Customer\s*No\.\s*\(Payer\)\s*\\n(\d{10})', text, re.I)
    if match:
        return match.group(1)
    return None

VENDOR_ACCOUNTS['Stericycle'] = {
    'has_account': True,
    'format': 'NNNNNNNNNN',
    'examples': ['3001288443', '3001313731'],
    'extract': _extract_stericycle
}


def _extract_tiger_sanitation(text: str) -> Optional[str]:
    """Format: 6-digit numeric after ACCOUNT NO
    V3 FIX: Search more broadly for the pattern
    Examples: 305967, 305949
    """
    lines = text.split('\\n')
    
    for i, line in enumerate(lines):
        if 'ACCOUNT NO' in line.upper():
            for j in range(i+1, min(i+5, len(lines))):
                val = lines[j].strip()
                match = re.match(r'^(\d{6})\b', val)
                if match:
                    return match.group(1)
    
    # Fallback: look for 6-digit near TIGER header
    for i, line in enumerate(lines):
        if 'TIGER' in line.upper():
            for j in range(i, min(i+20, len(lines))):
                val = lines[j].strip()
                if re.match(r'^\d{6}$', val):
                    return val
    
    # Original pattern with pipe separator
    match = re.search(r'ACCOUNT\s*NO\s*\|\s*INVOICE\s*DATE\s*\\n(\d{6})', text, re.I)
    if match:
        return match.group(1)
    
    return None

VENDOR_ACCOUNTS['Tiger Sanitation'] = {
    'has_account': True,
    'format': 'NNNNNN',
    'examples': ['305967', '305949'],
    'extract': _extract_tiger_sanitation
}


def _extract_troiano_waste(text: str) -> Optional[str]:
    """Format: 6-digit numeric CUSTOMER NO
    Examples: 022308
    """
    match = re.search(r'CUSTOMER\s*NO\s*\\n[A-Z]*\\n?(\d{6})', text, re.I)
    if match:
        return match.group(1)
    return None

VENDOR_ACCOUNTS['Troiano Waste'] = {
    'has_account': True,
    'format': 'NNNNNN',
    'examples': ['022308'],
    'extract': _extract_troiano_waste
}


def _extract_basin_disposal(text: str) -> Optional[str]:
    """Format: 7-digit numeric ACCOUNT:
    Examples: 1934769, 1934772
    """
    match = re.search(r'ACCOUNT:\s*(\d{7})', text, re.I)
    if match:
        return match.group(1)
    return None

VENDOR_ACCOUNTS['Basin Disposal'] = {
    'has_account': True,
    'format': 'NNNNNNN',
    'examples': ['1934769', '1934772'],
    'extract': _extract_basin_disposal_v3
}


def _extract_ghw_waste(text: str) -> Optional[str]:
    """Format: 4-digit numeric CUSTOMER NO.
    Examples: 1699, 2259
    """
    match = re.search(r'CUSTOMER\s*NO\.?\s*\\n(\d{4})', text, re.I)
    if match:
        return match.group(1)
    return None

VENDOR_ACCOUNTS['GHW Waste'] = {
    'has_account': True,
    'format': 'NNNN',
    'examples': ['1699', '2259'],
    'extract': _extract_ghw_waste
}


def _extract_patriot_waste(text: str) -> Optional[str]:
    """Format: 6-digit numeric CUSTOMER NO.
    Examples: 439822, 439827
    """
    match = re.search(r'CUSTOMER\s*NO\.?\s*\\n(\d{6})', text, re.I)
    if match:
        return match.group(1)
    return None

VENDOR_ACCOUNTS['Patriot Waste'] = {
    'has_account': True,
    'format': 'NNNNNN',
    'examples': ['439822', '439827'],
    'extract': _extract_patriot_waste_v3
}


def _extract_wasatch_waste(text: str) -> Optional[str]:
    """Format: 5-digit numeric (preceded by . in OCR)
    Examples: 80111, 80038
    """
    match = re.search(r'\.(\d{5})', text)
    return match.group(1) if match else None

VENDOR_ACCOUNTS['Wasatch Waste'] = {
    'has_account': True,
    'format': 'NNNNN',
    'examples': ['80111', '80038'],
    'extract': _extract_wasatch_waste
}


def _extract_apex_waste(text: str) -> Optional[str]:
    """Format: 6-10 digit numeric
    Examples: 10147921, 10128305
    """
    lines = text.split('\\n')
    for i, line in enumerate(lines):
        if 'CUSTOMER NO' in line.upper() or 'ACCOUNT' in line.upper():
            for j in range(i+1, min(i+5, len(lines))):
                val = lines[j].strip()
                if re.match(r'^\d{4,10}$', val):
                    return val
    return None

VENDOR_ACCOUNTS['Apex Waste'] = {
    'has_account': True,
    'format': 'NNNNNNNN',
    'examples': ['10147921', '10128305'],
    'extract': _extract_apex_waste_v3
}


def _extract_my_trash(text: str) -> Optional[str]:
    """Format: 10-digit numeric
    Examples: 1016024976
    """
    match = re.search(r'(?:Account|Customer)\s*(?:#|No)\.?:?\s*(\d{8,12})', text, re.I)
    return match.group(1) if match else None

VENDOR_ACCOUNTS['My Trash'] = {
    'has_account': True,
    'format': 'NNNNNNNNNN',
    'examples': ['1016024976'],
    'extract': _extract_my_trash
}


def _extract_huntsville_hauling(text: str) -> Optional[str]:
    """Format: NN-NNNNNNN N (Account No.)
    Examples: 77-1002382 4, 77-10023758
    """
    match = re.search(r'Account\s*No\.?\s*(\d{2}-\d{7}\s*\d?)', text, re.I)
    return match.group(1).strip() if match else None

VENDOR_ACCOUNTS['Huntsville Hauling'] = {
    'has_account': True,
    'format': 'NN-NNNNNNN N',
    'examples': ['77-1002382 4', '77-10023758'],
    'extract': _extract_huntsville_hauling
}


def _extract_waste_zero(text: str) -> Optional[str]:
    """Format: Multiple - Recology (9-10 digit), Zero Waste NH (4-6 digit)
    Examples: 0005298824, 8100237262, 5326, 1080914879
    Note: Multiple invoice systems detected as "Waste Zero"
    """
    lines = text.replace('\\n', '\n').split('\n')

    # Format 1: Recology columnar - Account Number: label with value on nearby line
    for i, line in enumerate(lines):
        if 'account number' in line.lower():
            for j in range(i, min(i+6, len(lines))):
                val = lines[j].strip()
                if re.match(r'^\d{9,10}$', val):
                    return val

    # Format 2: Recology - Customer\nNumber followed by 9-10 digit
    for i, line in enumerate(lines):
        if line.strip() == 'Customer':
            if i+1 < len(lines) and lines[i+1].strip() == 'Number':
                for j in range(i+2, min(i+10, len(lines))):
                    val = lines[j].strip()
                    if re.match(r'^\d{9,10}$', val):
                        return val

    # Format 3: Account Number inline
    match = re.search(r'Account\s*Number[:\s]*(\d{9,10})', text, re.I)
    if match:
        return match.group(1)

    # Format 4: Zero Waste NH - CUSTOMER NO. with nearby 4-6 digit number
    for i, line in enumerate(lines):
        if 'CUSTOMER NO' in line.upper():
            for j in range(max(0, i-5), min(i+5, len(lines))):
                val = lines[j].strip()
                if re.match(r'^\d{4,6}$', val):
                    return val

    return None

VENDOR_ACCOUNTS['Waste Zero'] = {
    'has_account': True,
    'format': 'NNNNNNNNNN',
    'examples': ['0005298824', '0043462481'],
    'extract': _extract_waste_zero
}


def _extract_ecosouth(text: str) -> Optional[str]:
    """Format: Alphanumeric XXXNNNNNN or numeric NNNNN
    V3 FIX: Skip payment receipts, handle Account\\nNumber header pattern
    Examples: MOBHC1227, UJ00110836, 14281
    """
    if 'Payment Successful' in text or 'Receipt of Payment' in text:
        return None
    
    lines = text.split('\\n')
    for i, line in enumerate(lines):
        if line.strip() == 'Account':
            if i+1 < len(lines) and 'Number' in lines[i+1]:
                for j in range(i+2, min(i+8, len(lines))):
                    val = lines[j].strip()
                    if val.startswith('INV') or '/' in val or val == '':
                        continue
                    if re.match(r'^[A-Z]{2,6}\d{4,8}$', val):
                        return val
                    if re.match(r'^\d{4,6}$', val):
                        return val
    
    # Pattern 2: Header format - Account Number inline
    match = re.search(r'Account\s*Number[:\s]*([A-Z]{2,6}\d{4,8}|\d{4,6})', text, re.I)
    if match:
        return match.group(1)
    return None

VENDOR_ACCOUNTS['EcoSouth'] = {
    'has_account': True,
    'format': 'XXXNNNNNN or NNNNN',
    'examples': ['MOBHC1227', 'UJ00110836', '14281'],
    'extract': _extract_ecosouth
}


def _extract_liberty_waste(text: str) -> Optional[str]:
    """Format: NN-NNNNN N
    Examples: 01-65907 7, 01-65820 2, 01-64506 8
    Note: Two invoice formats - Statement (Customer #:) and Invoice (Account No.)
    """
    # Pattern 1: Statement format - Customer #: NN-NNNNN N
    match = re.search(r'Customer\s*#:\s*(\d{2}-\d{5}\s*\d)', text, re.I)
    if match:
        return match.group(1).strip()
    
    # Pattern 2: Invoice format - Account No. NN-NNNNN N
    match = re.search(r'Account\s*No\.?\s*(\d{2}-\d{5}\s*\d)', text, re.I)
    if match:
        return match.group(1).strip()
    
    return None

VENDOR_ACCOUNTS['Liberty Waste'] = {
    'has_account': True,
    'format': 'NN-NNNNN N',
    'examples': ['01-65907 7', '01-65820 2'],
    'extract': _extract_liberty_waste
}


def _extract_el_harvey(text: str) -> Optional[str]:
    """Format: Waste Connections subsidiary - DDDD-NNNNNNNNN
    Examples: 6390-111705333, 6390-111705329
    """
    match = re.search(r'(\d{4}-\d{5,9})', text)
    return match.group(1) if match else None

VENDOR_ACCOUNTS['EL Harvey'] = {
    'has_account': True,
    'format': 'DDDD-NNNNNNNNN',
    'examples': ['6390-111705333', '6390-111705329'],
    'extract': _extract_el_harvey
}


def _extract_walters_recycling(text: str) -> Optional[str]:
    """Format: 5-8 digit numeric CUSTOMER ID
    Examples: 249297, 254922
    """
    lines = text.split('\\n')
    for i, line in enumerate(lines):
        if 'CUSTOMER ID' in line.upper():
            for j in range(i+1, min(i+5, len(lines))):
                val = lines[j].strip()
                if re.match(r'^\d{5,8}$', val):
                    return val
    return None

VENDOR_ACCOUNTS['Walters Recycling'] = {
    'has_account': True,
    'format': 'NNNNNN',
    'examples': ['249297', '254922'],
    'extract': _extract_walters_recycling
}


def _extract_sbc_waste(text: str) -> Optional[str]:
    """Format: NN-NNNNNNN N
    Examples: 10-2770100 1, 10-2770500 2, 10-3323705 7
    V6 FIX: Handle same-line format (NG invoices)
    """
    # Format 1: Same line - Account Number NN-NNNNNNN
    match = re.search(r'Account Number\s*(\d{2}-\d{7})', text, re.I)
    if match:
        return match.group(1)

    # Format 2: Separate lines
    lines = text.split('\\n')
    for i, line in enumerate(lines):
        if 'Account Number' in line:
            for j in range(i+1, min(i+8, len(lines))):
                val = lines[j].strip()
                if re.match(r'^\d{2}-\d{7}\s*\d?$', val):
                    return val
    return None

VENDOR_ACCOUNTS['SBC Waste'] = {
    'has_account': True,
    'format': 'NN-NNNNNNN N',
    'examples': ['10-2770100 1', '10-2770500 2'],
    'extract': _extract_sbc_waste
}


def _extract_interstate_waste(text: str) -> Optional[str]:
    """Format: 6-digit numeric Account Number
    Examples: 752073, 789063
    """
    lines = text.split('\\n')
    for i, line in enumerate(lines):
        if 'Account Number' in line:
            match = re.search(r'Account\s*Number:\s*(\d{6})', line, re.I)
            if match:
                return match.group(1)
            for j in range(i+1, min(i+5, len(lines))):
                val = lines[j].strip()
                if re.match(r'^\d{6}$', val):
                    return val
    return None

VENDOR_ACCOUNTS['Interstate Waste'] = {
    'has_account': True,
    'format': 'NNNNNN',
    'examples': ['752073', '789063'],
    'extract': _extract_interstate_waste
}


def _extract_ram_waste(text: str) -> Optional[str]:
    """Format: Waste Connections subsidiary - DDDD-NNNNNNNN
    Examples: 5327-31315501, 5327-31315495
    """
    match = re.search(r'(\d{4}-\d{5,9})', text)
    return match.group(1) if match else None

VENDOR_ACCOUNTS['RAM Waste'] = {
    'has_account': True,
    'format': 'DDDD-NNNNNNNN',
    'examples': ['5327-31315501', '5327-31315495'],
    'extract': _extract_ram_waste
}


def _extract_idaho_falls(text: str) -> Optional[str]:
    """Format: 7-digit numeric Account Number
    Examples: 2104954, 2104962
    """
    lines = text.split('\\n')
    for i, line in enumerate(lines):
        if 'Account Number' in line:
            for j in range(i+1, min(i+3, len(lines))):
                val = lines[j].strip()
                if re.match(r'^\d{6,8}$', val):
                    return val
    return None

VENDOR_ACCOUNTS['Idaho Falls Utilities'] = {
    'has_account': True,
    'format': 'NNNNNNN',
    'examples': ['2104954', '2104962'],
    'extract': _extract_idaho_falls
}


def _extract_nitti_sanitation(text: str) -> Optional[str]:
    """Format: 5-digit numeric on line 14
    Examples: 43498, 31825
    """
    lines = text.split('\\n')
    if len(lines) > 14:
        val = lines[14].strip()
        if re.match(r'^\d{4,6}$', val):
            return val
    return None

VENDOR_ACCOUNTS['Nitti Sanitation'] = {
    'has_account': True,
    'format': 'NNNNN',
    'examples': ['43498', '31825'],
    'extract': _extract_nitti_sanitation
}


def _extract_kmg_hauling(text: str) -> Optional[str]:
    """Format: 6-digit numeric CUSTOMER NO
    Examples: 005522, 005529
    """
    lines = text.split('\\n')
    for i, line in enumerate(lines):
        if 'CUSTOMER NO' in line.upper():
            if i+1 < len(lines):
                val = lines[i+1].strip()
                if re.match(r'^\d{5,8}$', val):
                    return val
    return None

VENDOR_ACCOUNTS['KMG Hauling'] = {
    'has_account': True,
    'format': 'NNNNNN',
    'examples': ['005522', '005529'],
    'extract': _extract_kmg_hauling
}


def _extract_empire_waste(text: str) -> Optional[str]:
    """Format: 4-6 digit numeric ACCOUNT #
    Examples: 1930, 2714
    """
    lines = text.split('\\n')
    for i, line in enumerate(lines):
        if 'ACCOUNT #' in line.upper():
            for j in range(i+1, min(i+6, len(lines))):
                val = lines[j].strip()
                if re.match(r'^\d{4,6}$', val):
                    return val
    return None

VENDOR_ACCOUNTS['Empire Waste'] = {
    'has_account': True,
    'format': 'NNNN',
    'examples': ['1930', '2714'],
    'extract': _extract_empire_waste
}


def _extract_eco_tech(text: str) -> Optional[str]:
    """Format: 7-digit numeric ACCOUNT#
    Examples: 7590401, 7960801
    """
    lines = text.split('\\n')
    for i, line in enumerate(lines):
        if 'ACCOUNT#' in line.upper():
            if i+1 < len(lines):
                val = lines[i+1].strip()
                if re.match(r'^\d{5,10}$', val):
                    return val
    return None

VENDOR_ACCOUNTS['Eco-Tech'] = {
    'has_account': True,
    'format': 'NNNNNNN',
    'examples': ['7590401', '7960801'],
    'extract': _extract_eco_tech
}


def _extract_edco_disposal(text: str) -> Optional[str]:
    """Format: NN-XX NNNNNN
    Examples: 56-K4 728368, 37-ER 720221
    """
    lines = text.split('\\n')
    for i, line in enumerate(lines):
        if 'Account Number' in line:
            for j in range(i+1, min(i+8, len(lines))):
                val = lines[j].strip()
                if re.match(r'^\d{2}-[A-Z0-9]{2}\s*\d{6}$', val):
                    return val
    return None

VENDOR_ACCOUNTS['EDCO Disposal'] = {
    'has_account': True,
    'format': 'NN-XX NNNNNN',
    'examples': ['56-K4 728368', '37-ER 720221'],
    'extract': _extract_edco_disposal
}


def _extract_metalpro(text: str) -> Optional[str]:
    """Format: 5-digit numeric Customer Number
    Examples: 13117
    """
    match = re.search(r'Customer\s*Number:\s*(\d{4,6})', text, re.I)
    return match.group(1) if match else None

VENDOR_ACCOUNTS['Metalpro'] = {
    'has_account': True,
    'format': 'NNNNN',
    'examples': ['13117'],
    'extract': _extract_metalpro_v3
}


def _extract_mountain_state_waste(text: str) -> Optional[str]:
    """Format: 7-digit numeric Account #
    Examples: 1309931, 1238548
    """
    lines = text.split('\\n')
    for i, line in enumerate(lines):
        if 'Account #' in line:
            for j in range(i+1, min(i+5, len(lines))):
                val = lines[j].strip()
                if re.match(r'^\d{5,8}$', val):
                    return val
    return None

VENDOR_ACCOUNTS['Mountain State Waste'] = {
    'has_account': True,
    'format': 'NNNNNNN',
    'examples': ['1309931', '1238548'],
    'extract': _extract_mountain_state_waste
}


def _extract_vls_environmental(text: str) -> Optional[str]:
    """Format: XNNNNN (letter + 5 digits)
    Examples: C08510
    Note: Columnar layout may have value before/after Customer ID label
    """
    lines = text.replace('\\n', '\n').split('\n')

    # Pattern 1: Find Customer ID label and search nearby lines (before and after)
    for i, line in enumerate(lines):
        if 'customer id' in line.lower():
            # Check lines before and after
            for j in range(max(0, i-5), min(i+5, len(lines))):
                val = lines[j].strip()
                if re.match(r'^[A-Z]\d{5}$', val):
                    return val

    # Pattern 2: Inline format
    match = re.search(r'Customer\s*ID[:\s]*([A-Z]\d{5})', text, re.I)
    if match:
        return match.group(1)

    return None

VENDOR_ACCOUNTS['VLS Environmental'] = {
    'has_account': True,
    'format': 'XNNNNN',
    'examples': ['C08510'],
    'extract': _extract_vls_environmental
}


def _extract_mark_dunning(text: str) -> Optional[str]:
    """Format: 7-digit numeric ACCOUNT#
    Examples: 1373624, 1347666
    """
    lines = text.split('\\n')
    for i, line in enumerate(lines):
        if 'ACCOUNT#' in line.upper():
            if i+1 < len(lines):
                val = lines[i+1].strip()
                if re.match(r'^\d{5,10}$', val):
                    return val
    return None

VENDOR_ACCOUNTS['Mark Dunning'] = {
    'has_account': True,
    'format': 'NNNNNNN',
    'examples': ['1373624', '1347666'],
    'extract': _extract_mark_dunning
}


def _extract_detroit_disposal(text: str) -> Optional[str]:
    """Format: 6-digit numeric Account Number
    Examples: 307400, 307201
    """
    lines = text.split('\\n')
    for i, line in enumerate(lines):
        if 'Account Number' in line:
            for j in range(i+1, min(i+5, len(lines))):
                val = lines[j].strip()
                if re.match(r'^\d{5,8}$', val):
                    return val
    return None

VENDOR_ACCOUNTS['Detroit Disposal'] = {
    'has_account': True,
    'format': 'NNNNNN',
    'examples': ['307400', '307201'],
    'extract': _extract_detroit_disposal
}


def _extract_jp_mascaro(text: str) -> Optional[str]:
    """Format: 6-digit numeric CUSTOMER NO.
    Examples: 132402, 187877
    """
    lines = text.split('\\n')
    for i, line in enumerate(lines):
        if 'CUSTOMER NO' in line.upper():
            for j in range(i+2, min(i+12, len(lines))):
                val = lines[j].strip()
                if re.match(r'^\d{6}$', val):
                    return val
    return None

VENDOR_ACCOUNTS['JP Mascaro'] = {
    'has_account': True,
    'format': 'NNNNNN',
    'examples': ['132402', '187877'],
    'extract': _extract_jp_mascaro
}


def _extract_american_recycling(text: str) -> Optional[str]:
    """Format: Alphanumeric Cust ID
    Examples: STANDARD-1, UPS-AVENEL
    """
    match = re.search(r'Cust\s*ID\s+([A-Z0-9\-]+)', text, re.I)
    return match.group(1) if match else None

VENDOR_ACCOUNTS['American Recycling'] = {
    'has_account': True,
    'format': 'XXXXX-N',
    'examples': ['STANDARD-1', 'UPS-AVENEL'],
    'extract': _extract_american_recycling
}


# ============================================================
# VENDORS WITHOUT ACCOUNT NUMBERS (Invoice-only identification)
# ============================================================


# ============================================================
# V4 NEW TRANCHE - 17 VENDORS (December 2024)
# ============================================================

def _extract_boro_wide(text: str) -> Optional[str]:
    """Format: LBP-NNNNNN, BP-NNNNNN, or NN-NNNNNNN (MRT merged format)
    Examples: LBP-000129, BP-008532, 02-3900232
    """
    # Pattern 1: LBP/BP prefix format
    match = re.search(r'Account\s*Number\s*[:\n\\n]?\s*([LB]?BP-\d{6})', text, re.I)
    if match:
        return match.group(1)
    # Pattern 2: MRT merged format (NN-NNNNNNN)
    match = re.search(r'CUSTOMER\s*NUMBER\s*[:\n\\n]?\s*(\d{2}-\d{7})', text, re.I)
    if match:
        return match.group(1)
    lines = text.split('\\n')
    for i, line in enumerate(lines):
        if 'Account Number' in line or 'CUSTOMER NUMBER' in line.upper():
            for j in range(i+1, min(i+5, len(lines))):
                val = lines[j].strip()
                if re.match(r'^[LB]?BP-\d{6}$', val) or re.match(r'^\d{2}-\d{7}$', val):
                    return val
    match = re.search(r'([LB]BP-\d{6})', text)
    if match:
        return match.group(1)
    match = re.search(r'(\d{2}-\d{7})', text)
    if match:
        return match.group(1)
    return None

def _extract_direct_waste_services(text: str) -> Optional[str]:
    """Format: NNNN (4-digit customer number)"""
    match = re.search(r'CUSTOMER\s*NO\s*[:\n\\n]?\s*(\d{4,6})', text, re.I)
    if match:
        return match.group(1)
    lines = text.split('\\n')
    for i, line in enumerate(lines):
        if 'CUSTOMER NO' in line.upper():
            m = re.search(r'(\d{4,6})', line)
            if m:
                return m.group(1)
            for j in range(i+1, min(i+5, len(lines))):
                val = lines[j].strip()
                if re.match(r'^\d{4,6}$', val):
                    return val
    return None

def _extract_cards_mo(text: str) -> Optional[str]:
    """Format: NN-NNNNN N (similar to Casella)"""
    match = re.search(r'Account\s*No\.?\s*(\d{2}-\d{5}\s*\d)', text, re.I)
    if match:
        return match.group(1).strip()
    match = re.search(r'(\d{2}-\d{5}\s+\d)\b', text)
    if match:
        return match.group(1).strip()
    return None

def _extract_chrin_hauling(text: str) -> Optional[str]:
    """Format: NNNNNN (6-digit)"""
    match = re.search(r'CUSTOMER\s*NO\s*[:\n\\n]?\s*(\d{6})', text, re.I)
    if match:
        return match.group(1)
    lines = text.split('\\n')
    for i, line in enumerate(lines):
        if 'CUSTOMER NO' in line.upper():
            m = re.search(r'(\d{6})', line)
            if m:
                return m.group(1)
            for j in range(i+1, min(i+5, len(lines))):
                val = lines[j].strip()
                if re.match(r'^\d{6}$', val):
                    return val
    return None

def _extract_roll_off_systems(text: str) -> Optional[str]:
    """Format: NNNNNN (6-digit)"""
    match = re.search(r'Customer\s*#\s*[:\n\\n]?\s*(\d{6})', text, re.I)
    if match:
        return match.group(1)
    lines = text.split('\\n')
    for i, line in enumerate(lines):
        if 'Customer #' in line:
            m = re.search(r'(\d{6})', line)
            if m:
                return m.group(1)
            for j in range(i+1, min(i+5, len(lines))):
                val = lines[j].strip()
                if re.match(r'^\d{6}$', val):
                    return val
    return None

def _extract_lakeshore_recycling(text: str) -> Optional[str]:
    """Format: NNNNN.N or NNNNN"""
    match = re.search(r'Customer\s*Number:\s*(\d{4,6}\.\d)', text, re.I)
    if match:
        return match.group(1)
    match = re.search(r'Customer\s*Number:\s*(\d{5,6})(?!\.\d)', text, re.I)
    if match:
        return match.group(1)
    match = re.search(r'(\d{4,6}\.\d)', text)
    if match:
        return match.group(1)
    return None

def _extract_waste_services_llc(text: str) -> Optional[str]:
    """Format: NNNNNN (TrashBilling, West Point only)"""
    if 'West Point Waste' in text or 'TrashBilling' in text:
        match = re.search(r'account\s*number\s*with\s*this\s*hauler\s*is\s*(\d{6})', text, re.I)
        if match:
            return match.group(1)
        match = re.search(r'ID#:\s*\d*(\d{6})', text)
        if match:
            return match.group(1)
    if 'North Charleston' in text or 'SC 29415' in text:
        return None
    match = re.search(r'account\s*number\s*with\s*this\s*hauler\s*is\s*(\d{6})', text, re.I)
    if match:
        return match.group(1)
    return None

def _extract_cooks_wastepaper(text: str) -> Optional[str]:
    """Format: DDDD-NNNNNN (Waste Connections format)"""
    match = re.search(r'ACCOUNT\s*NO\.?\s*[:\n\\n]?\s*(\d{4}-\d{6})', text, re.I)
    if match:
        return match.group(1)
    match = re.search(r'Acct\s*#\s*(\d{4}-\d{6})', text, re.I)
    if match:
        return match.group(1)
    match = re.search(r'(3032-\d{6})', text)
    if match:
        return match.group(1)
    return None

def _extract_eoms_recycling(text: str) -> Optional[str]:
    """Format: 12-digit TrashBilling ID"""
    match = re.search(r'ID#:\s*(\d{12})', text)
    if match:
        return match.group(1)
    match = re.search(r'Customer\s*Information\s*[:\n\\n]?\s*(\d{12})', text, re.I)
    if match:
        return match.group(1)
    return None

def _extract_mid_valley_disposal(text: str) -> Optional[str]:
    """Format: NNNNNNNN (8-digit)"""
    match = re.search(r'Account\s*Number\s*[:\n\\n]?\s*(\d{8})', text, re.I)
    if match:
        return match.group(1)
    lines = text.split('\\n')
    for i, line in enumerate(lines):
        if 'Account Number' in line:
            m = re.search(r'(\d{8})', line)
            if m:
                return m.group(1)
            for j in range(i+1, min(i+5, len(lines))):
                val = lines[j].strip()
                if re.match(r'^\d{8}$', val):
                    return val
    return None

def _extract_modern_corporation(text: str) -> Optional[str]:
    """Format: NNNNN (5-digit customer)"""
    match = re.search(r'Customer\s*Number:\s*(\d{5,6})', text, re.I)
    if match:
        return match.group(1)
    lines = text.split('\\n')
    for i, line in enumerate(lines):
        if 'Customer Number:' in line:
            m = re.search(r'(\d{5,6})', line)
            if m:
                return m.group(1)
            for j in range(i+1, min(i+5, len(lines))):
                val = lines[j].strip()
                if re.match(r'^\d{5,6}$', val):
                    return val
    return None

def _extract_atlantic_waste(text: str) -> Optional[str]:
    """Format: NNNNNNNNN (9-digit)"""
    match = re.search(r'Account\s*Number\s*[:\n\\n]?\s*(\d{9})', text, re.I)
    if match:
        return match.group(1)
    lines = text.split('\\n')
    for i, line in enumerate(lines):
        if 'Account Number' in line:
            m = re.search(r'(\d{9})', line)
            if m:
                return m.group(1)
            for j in range(i+1, min(i+5, len(lines))):
                val = lines[j].strip()
                if re.match(r'^\d{9}$', val):
                    return val
    match = re.search(r'ActNbr:\s*(\d{9})', text)
    if match:
        return match.group(1)
    return None

def _extract_vista_recycling(text: str) -> Optional[str]:
    """Format: NNNNNNN (7-digit)"""
    match = re.search(r'Account\s*Number\s*[:\n\\n]?\s*(\d{7})', text, re.I)
    if match:
        return match.group(1)
    lines = text.split('\\n')
    for i, line in enumerate(lines):
        if 'Account Number' in line:
            m = re.search(r'(\d{7})', line)
            if m:
                return m.group(1)
            for j in range(i+1, min(i+5, len(lines))):
                val = lines[j].strip()
                if re.match(r'^\d{7}$', val):
                    return val
    return None

def _extract_ace_waste_systems(text: str) -> Optional[str]:
    """Format: NN-NNNNN N"""
    match = re.search(r'Customer\s*#:\s*(\d{2}-\d{5}\s*\d)', text, re.I)
    if match:
        return match.group(1).strip()
    match = re.search(r'(\d{2}-\d{5}\s+\d)\b', text)
    if match:
        return match.group(1).strip()
    return None

def _extract_schaap_sanitation(text: str) -> Optional[str]:
    """Format: DDDD-NNNNNN(-NNN) (Waste Connections format)"""
    match = re.search(r'ACCOUNT\s*NO\.?\s*[:\n\\n]?\s*(\d{4}-\d{6}(?:-\d{3})?)', text, re.I)
    if match:
        return match.group(1)
    match = re.search(r'Acct\s*#\s*(\d{4}-\d{6}(?:-\d{3})?)', text, re.I)
    if match:
        return match.group(1)
    match = re.search(r'(3061-\d{6}(?:-\d{3})?)', text)
    if match:
        return match.group(1)
    return None


# V4 Vendor Registrations
VENDOR_ACCOUNTS['Boro Wide'] = {
    'has_account': True,
    'format': 'LBP-NNNNNN/BP-NNNNNN/NN-NNNNNNN',
    'examples': ['LBP-000129', 'BP-008532', '02-3900232'],
    'extract': _extract_boro_wide
}

VENDOR_ACCOUNTS['Direct Waste Services'] = {
    'has_account': True,
    'format': 'NNNN',
    'examples': ['6723'],
    'extract': _extract_direct_waste_services
}

VENDOR_ACCOUNTS['Cards Mo'] = {
    'has_account': True,
    'format': 'NN-NNNNN N',
    'examples': ['12-12753 7', '12-12752 9'],
    'extract': _extract_cards_mo
}

VENDOR_ACCOUNTS['Chrin Hauling'] = {
    'has_account': True,
    'format': 'NNNNNN',
    'examples': ['907454', '926598'],
    'extract': _extract_chrin_hauling
}

VENDOR_ACCOUNTS['Roll Off Systems'] = {
    'has_account': True,
    'format': 'NNNNNN',
    'examples': ['015598'],
    'extract': _extract_roll_off_systems
}

VENDOR_ACCOUNTS['Lakeshore Recycling'] = {
    'has_account': True,
    'format': 'NNNNN.N or NNNNN',
    'examples': ['5824.9', '62646.2', '38943'],
    'extract': _extract_lakeshore_recycling
}

VENDOR_ACCOUNTS['Waste Services LLC'] = {
    'has_account': True,
    'format': 'NNNNNN (TrashBilling)',
    'examples': ['000760'],
    'extract': _extract_waste_services_llc
}

VENDOR_ACCOUNTS['Cooks Wastepaper'] = {
    'has_account': True,
    'format': 'DDDD-NNNNNN',
    'examples': ['3032-116997', '3032-130986'],
    'extract': _extract_cooks_wastepaper
}

VENDOR_ACCOUNTS['EOMS Recycling'] = {
    'has_account': True,
    'format': 'NNNNNNNNNNNN',
    'examples': ['108550126510', '108550130158'],
    'extract': _extract_eoms_recycling
}

VENDOR_ACCOUNTS['Mid Valley Disposal'] = {
    'has_account': True,
    'format': 'NNNNNNNN',
    'examples': ['67204800', '68781900'],
    'extract': _extract_mid_valley_disposal
}

VENDOR_ACCOUNTS['Modern Corporation'] = {
    'has_account': True,
    'format': 'NNNNN',
    'examples': ['53262'],
    'extract': _extract_modern_corporation
}

VENDOR_ACCOUNTS['Atlantic Waste'] = {
    'has_account': True,
    'format': 'NNNNNNNNN',
    'examples': ['921935800', '883410000'],
    'extract': _extract_atlantic_waste
}

VENDOR_ACCOUNTS['Vista Recycling'] = {
    'has_account': True,
    'format': 'NNNNNNN',
    'examples': ['2471700', '2471600'],
    'extract': _extract_vista_recycling
}

VENDOR_ACCOUNTS['Ace Waste Systems'] = {
    'has_account': True,
    'format': 'NN-NNNNN N',
    'examples': ['01-22629 9', '01-17968 8'],
    'extract': _extract_ace_waste_systems
}

VENDOR_ACCOUNTS['Schaap Sanitation'] = {
    'has_account': True,
    'format': 'DDDD-NNNNNN(-NNN)',
    'examples': ['3061-216805-005', '3061-295662'],
    'extract': _extract_schaap_sanitation
}


# ============================================================
# V5 EXTRACTION FUNCTIONS - TRANCHE 1 (December 2024)
# ============================================================

def _extract_cockeys_enterprises(text: str) -> Optional[str]:
    """
    Cockey's Enterprises - Format: NNNNN or NNNNN-NNN (5-digit, optionally with site suffix)
    Examples: 13010, 13010-007, 13010-035
    Pattern: ACCOUNT # header/inline, return base account (first 5 digits)
    """
    lines = text.split('\\n')
    
    # Pattern 1: ACCOUNT # inline with value (statement format)
    match = re.search(r'ACCOUNT\s*#\s*[:\n\\n]?\s*(\d{5})(?:-\d{3})?', text, re.I)
    if match:
        return match.group(1)
    
    # Pattern 2: Account #: inline format
    match = re.search(r'Account\s*#:\s*(\d{5})(?:-\d{3})?', text, re.I)
    if match:
        return match.group(1)
    
    # Pattern 3: ACCOUNT # header with value below (columnar OCR - portal format)
    for i, line in enumerate(lines):
        if 'ACCOUNT #' in line.upper() and 'SITE' not in line.upper():
            for j in range(i+1, min(i+8, len(lines))):
                val = lines[j].strip()
                # Match 5-digit or 5-digit-3-digit
                m = re.match(r'^(\d{5})(?:-\d{3})?$', val)
                if m:
                    return m.group(1)
    
    # Pattern 4: Site pattern with account prefix (e.g., Site 13010132)
    match = re.search(r'Site\s+(\d{5})\d{3}\s*-', text)
    if match:
        return match.group(1)
    
    return None


def _extract_harters(text: str) -> Optional[str]:
    """
    Harter's - Multiple formats:
    - NN-NNNNN N (Fox Valley Disposal brand, check digit format)
    - NNNNNN (Quick Clean Up brand, 6-digit)
    Examples: 01-65024 1, 01-82266 7, 023401, 023912
    """
    # Pattern 1: Customer #: followed by check digit format (Fox Valley)
    match = re.search(r'Customer\s*#:\s*(\d{2}-\d{5}\s*\d)', text, re.I)
    if match:
        return match.group(1).strip()
    
    # Pattern 2: Customer Nbr header followed by 6-digit (Quick Clean Up)
    lines = text.split('\\n')
    for i, line in enumerate(lines):
        if 'Customer Nbr' in line:
            for j in range(i+1, min(i+3, len(lines))):
                val = lines[j].strip()
                if re.match(r'^\d{6}$', val):
                    return val
    
    # Pattern 3: Standalone NN-NNNNN N format
    match = re.search(r'\b(\d{2}-\d{5}\s+\d)\b', text)
    if match:
        return match.group(1).strip()
    
    return None


def _extract_city_of_meridian(text: str) -> Optional[str]:
    """
    City of Meridian - Format: NNNNNNNN-NN (8 digits dash 2 digits)
    Examples: 99011222-01, 99011234-01
    Pattern: Account: followed by value
    """
    # Pattern 1: Account: inline
    match = re.search(r'Account:\s*(\d{8}-\d{2})', text, re.I)
    if match:
        return match.group(1)
    
    # Pattern 2: Account No.: format
    match = re.search(r'Account\s*No\.?:\s*(\d{8}-\d{2})', text, re.I)
    if match:
        return match.group(1)
    
    # Pattern 3: Look for pattern in barcode area
    match = re.search(r'\*\s*(\d{8}-\d{2})\s*\*', text)
    if match:
        return match.group(1)
    
    # Pattern 4: Standalone 8-2 format near Account context
    lines = text.split('\\n')
    for i, line in enumerate(lines):
        if 'Account' in line:
            m = re.search(r'(\d{8}-\d{2})', line)
            if m:
                return m.group(1)
            for j in range(i+1, min(i+3, len(lines))):
                m = re.search(r'(\d{8}-\d{2})', lines[j])
                if m:
                    return m.group(1)
    
    return None


def _extract_blue_diamond_disposal(text: str) -> Optional[str]:
    """
    Blue Diamond Disposal - Format: NNNNN (5-digit)
    Examples: 30239
    Pattern: CUSTOMER NO. - columnar OCR where value appears BEFORE header
    """
    lines = text.split('\\n')
    
    # Pattern 1: Columnar OCR - Look for 5-digit value after date pattern (Mmm-DD-YY)
    # In the OCR: DATE value, then CUSTOMER NO value, then headers come later
    for i, line in enumerate(lines):
        # Look for date pattern like "Jul-15-25"
        if re.match(r'^[A-Z][a-z]{2}-\d{1,2}-\d{2}$', line.strip()):
            # Next line should be customer number
            if i + 1 < len(lines):
                val = lines[i + 1].strip()
                if re.match(r'^\d{5}$', val):
                    return val
    
    # Pattern 2: CUSTOMER NO. inline (remittance section)
    match = re.search(r'CUSTOMER\s*NO\.?\s*[:\n\\n]?\s*(\d{5})', text, re.I)
    if match:
        return match.group(1)
    
    # Pattern 3: Look in columnar format - value BEFORE header
    for i, line in enumerate(lines):
        if 'CUSTOMER NO' in line.upper():
            # Check lines BEFORE the header (OCR column inversion)
            for j in range(max(0, i-8), i):
                val = lines[j].strip()
                if re.match(r'^\d{5}$', val):
                    return val
    
    return None


def _extract_valley_vista(text: str) -> Optional[str]:
    """
    Valley Vista - Multiple formats:
    - VV-NNNNNN N (VV prefix + 6 digits + check digit)
    - NN-NNNNN N (2 digit prefix + 5 digits + check digit, Ware Disposal brand)
    - VV-NNNNNNN (VV prefix + 7 digits, Co-Cust# format)
    - VC-NNNNNNN (VC prefix + 7 digits, Orange County format)
    Examples: VV-478887 7, VV-478891 9, 01-30289 2, VV-0483488, VC-4556236
    """
    # Pattern 1: VV- or VC- format (7 digits, optional check digit)
    match = re.search(r'\b(V[VC]-\d{6,7}\s*\d?)\b', text)
    if match:
        return match.group(1).strip()
    
    # Pattern 2: Account Number header followed by VV-/VC- format
    match = re.search(r'Account\s*Number[:\n\\n]?\s*(V[VC]-\d{6,7}\s*\d?)', text, re.I)
    if match:
        return match.group(1).strip()
    
    # Pattern 3: Co-Cust#: format (A/R reports)
    match = re.search(r'Co-Cust#:\s*(VV-\d{7})', text)
    if match:
        return match.group(1)
    
    # Pattern 4: NN-NNNNN N format (Ware Disposal brand)
    lines = text.split('\\n')
    for i, line in enumerate(lines):
        if 'Account #' in line or 'Account Number' in line:
            for j in range(i+1, min(i+8, len(lines))):
                val = lines[j].strip()
                # Match VV-/VC- format or NN-NNNNN N format
                m = re.match(r'^(V[VC]-\d{6,7}\s*\d?|\d{2}-\d{5}\s+\d)$', val)
                if m:
                    return m.group(1).strip()
    
    # Pattern 5: Standalone NN-NNNNN N format near Account context
    match = re.search(r'Account\s*#?\s*\\n.*?(\d{2}-\d{5}\s+\d)', text)
    if match:
        return match.group(1).strip()
    
    return None


def _extract_ssw_frontload(text: str) -> Optional[str]:
    """
    SSW Frontload - Format: NNNN-NNNNNN (4-6 digit, may have leading zeros)
    Examples: 6215, 5617, 003910, 005617
    Pattern: TrashBilling style - Acct# or "account number with this hauler"
    """
    # Pattern 1: "account number with this hauler is" (payment confirmations)
    match = re.search(r'account\s*number\s*with\s*this\s*hauler\s*is\s*(\d{4,6})', text, re.I)
    if match:
        return match.group(1)
    
    # Pattern 2: Acct# inline (invoice format)
    match = re.search(r'Acct#\s*(\d{4,6})\b', text, re.I)
    if match:
        return match.group(1)
    
    # Pattern 3: ID#: TrashBilling format - extract account from 12-digit ID
    # Format: 585660XXXXXX where XXXXXX contains account
    match = re.search(r'ID#:\s*\d{6}0*(\d{4,6})\d*', text)
    if match:
        return match.group(1)
    
    return None


def _extract_velpen_trucking(text: str) -> Optional[str]:
    """
    Velpen Trucking - Format: NNNNNN (6-digit, may have leading zeros)
    Examples: 006509, 052698
    Pattern: TrashBilling - "account number with this hauler is" or ID#
    """
    # Pattern 1: "account number with this hauler is"
    match = re.search(r'account\s*number\s*with\s*this\s*hauler\s*is\s*(\d{6})', text, re.I)
    if match:
        return match.group(1)
    
    # Pattern 2: ID#: format - extract last 6 digits before final 2
    match = re.search(r'ID#:\s*\d{6}(\d{6})\d*', text)
    if match:
        return match.group(1)
    
    # Pattern 3: Customer Info section with ID format
    match = re.search(r'Customer\s*Information\s*\\n(\d+)', text)
    if match:
        val = match.group(1)
        if len(val) >= 6:
            return val[-8:-2] if len(val) > 8 else val[:6]
    
    return None


def _extract_gotta_go_waste(text: str) -> Optional[str]:
    """
    Gotta Go Waste - Format: NNNN (4-digit) or NNNNNN (6-digit with leading zeros)
    Examples: 7933, 007933
    Pattern: Columnar OCR - Customer header with value 6 rows below, or transaction records
    Note: Filters out "Zach Erwin Construction dba Gotta GO" (different company)
    """
    # Filter: Different company with similar name
    if 'Zach Erwin' in text or 'Nevada MO' in text:
        return None
    
    lines = text.split('\\n')
    
    # Pattern 1: Transaction record format - "007933 - Wasteology"
    match = re.search(r'(\d{6})\s*-\s*Wasteology', text, re.I)
    if match:
        # Strip leading zeros but keep at least the last 4 digits
        acct = match.group(1).lstrip('0') or match.group(1)[-4:]
        return acct
    
    # Pattern 2: Columnar OCR - headers (Invoice, Page, Date, Customer, Site, PO Number)
    # followed by values 6 rows later
    for i, line in enumerate(lines):
        if line.strip() == 'Customer':
            # Value appears about 6 lines after the header
            for j in range(i+4, min(i+10, len(lines))):
                val = lines[j].strip()
                if re.match(r'^\d{4}$', val):
                    return val
    
    # Pattern 3: Customer followed by value on same line
    match = re.search(r'\bCustomer\s+(\d{4})\b', text)
    if match:
        return match.group(1)
    
    return None


def _extract_louisiana_waste(text: str) -> Optional[str]:
    """
    Louisiana Waste - Format: NNNN (4-digit)
    Examples: 3704
    Pattern: Same as Cockey's - ACCOUNT # header style
    """
    lines = text.split('\\n')
    
    # Pattern 1: ACCOUNT # header with value below
    for i, line in enumerate(lines):
        if 'ACCOUNT #' in line.upper():
            for j in range(i+1, min(i+8, len(lines))):
                val = lines[j].strip()
                if re.match(r'^\d{4}$', val):
                    return val
    
    # Pattern 2: Site pattern with account prefix
    match = re.search(r'Site\s+(\d{4})\d{3}\s*-', text)
    if match:
        return match.group(1)
    
    return None


# V5 Vendor Registrations - Tranche 1
VENDOR_ACCOUNTS["Cockey's Enterprises"] = {
    'has_account': True,
    'format': 'NNNNN',
    'examples': ['13010'],
    'extract': _extract_cockeys_enterprises
}

VENDOR_ACCOUNTS["Harter's"] = {
    'has_account': True,
    'format': 'NN-NNNNN N / NNNNNN',
    'examples': ['01-65024 1', '023401'],
    'extract': _extract_harters
}

VENDOR_ACCOUNTS['City of Meridian'] = {
    'has_account': True,
    'format': 'NNNNNNNN-NN',
    'examples': ['99011222-01', '99011234-01'],
    'extract': _extract_city_of_meridian
}

VENDOR_ACCOUNTS['Blue Diamond Disposal'] = {
    'has_account': True,
    'format': 'NNNNN',
    'examples': ['30239'],
    'extract': _extract_blue_diamond_disposal
}

VENDOR_ACCOUNTS['Valley Vista'] = {
    'has_account': True,
    'format': 'VV-NNNNNN N / VC-NNNNNNN / NN-NNNNN N',
    'examples': ['VV-478887 7', 'VC-4556236', '01-30289 2'],
    'extract': _extract_valley_vista
}

VENDOR_ACCOUNTS['SSW Frontload'] = {
    'has_account': True,
    'format': 'NNNN',
    'examples': ['6215', '5617'],
    'extract': _extract_ssw_frontload
}

VENDOR_ACCOUNTS['Velpen Trucking'] = {
    'has_account': True,
    'format': 'NNNNNN',
    'examples': ['006509', '052698'],
    'extract': _extract_velpen_trucking
}

VENDOR_ACCOUNTS['Gotta Go Waste'] = {
    'has_account': True,
    'format': 'NNNN',
    'examples': ['7933'],
    'extract': _extract_gotta_go_waste
}

VENDOR_ACCOUNTS['Louisiana Waste'] = {
    'has_account': True,
    'format': 'NNNN',
    'examples': ['3704'],
    'extract': _extract_louisiana_waste
}


# ============================================================
# V5 EXTRACTION FUNCTIONS - TRANCHE 2 (December 2024)
# ============================================================

def _extract_abc_waste(text: str) -> Optional[str]:
    """
    ABC Waste - Format: NN-NNNN(N) N or NN-NNNNNNN (with/without check digit)
    Examples: 10-339800 4, 10-3471256, 10-4725 7
    Pattern: Account No. inline
    """
    # Pattern 1: Account No. with check digit format (4-7 digits in middle)
    match = re.search(r'Account\s*No\.?\s*(\d{2}-\d{4,7}\s*\d?)', text, re.I)
    if match:
        return match.group(1).strip()
    
    # Pattern 2: Account No.: inline
    match = re.search(r'Account\s*No\.?:\s*(\d{2}-\d{4,7}\s*\d?)', text, re.I)
    if match:
        return match.group(1).strip()
    
    return None


def _extract_smith_creek(text: str) -> Optional[str]:
    """
    Smith Creek - Format: WASTNNN (WAST + 4 digits)
    Examples: WAST0004
    Pattern: Customer code in header area
    """
    # Pattern 1: WAST followed by 4 digits (no word boundary due to \\n issues)
    match = re.search(r'(WAST\d{4})', text)
    if match:
        return match.group(1)
    
    return None


def _extract_jlt_trucking(text: str) -> Optional[str]:
    """
    JLT Trucking - Format: NNNNNNN (7-digit)
    Examples: 1001434
    Pattern: ACCOUNT # header (same portal format as Cockey's/Louisiana Waste)
    """
    lines = text.split('\\n')
    
    # Pattern 1: ACCOUNT # header followed by value
    for i, line in enumerate(lines):
        if 'ACCOUNT #' in line.upper():
            for j in range(i+1, min(i+8, len(lines))):
                val = lines[j].strip()
                if re.match(r'^\d{7}$', val):
                    return val
    
    # Pattern 2: Site pattern with account prefix
    match = re.search(r'Site\s+(\d{7})\d{3}\s*-', text)
    if match:
        return match.group(1)
    
    return None


def _extract_liberty_disposal(text: str) -> Optional[str]:
    """
    Liberty Disposal - Multiple formats:
    - NNNNXX (4 digits + 2 letters) e.g., 2476TU
    - NNNNNX (5 digits + 1 letter) e.g., 15990C  
    - NNNN (4 digits) for TrashBilling e.g., 1599
    - NNNNNN (6 digits) for scale tickets e.g., 019022
    - NNNNNNNNNNNN (12 digits) for payment confirmations e.g., 731810015990
    Pattern: ACCOUNT NO for invoices, CUSTOMER for scale tickets, Account # for TrashBilling
    """
    lines = text.split('\\n')
    
    # Pattern 1: Payment confirmation format - 12 digit after Customer Information
    if 'Customer Information' in text:
        match = re.search(r'Customer Information\s*\\n(\d{12})', text)
        if match:
            return match.group(1)
    
    # Pattern 2: TrashBilling format - Account #: NNNN or Acct# NNNN
    match = re.search(r'Account\s*#:\s*\\n?(\d{4})\b', text, re.I)
    if match:
        return match.group(1)
    match = re.search(r'Acct#\s*(\d{4})\b', text, re.I)
    if match:
        return match.group(1)
    
    # Pattern 3: Invoice format - ACCOUNT NO header with value 6 rows below
    for i, line in enumerate(lines):
        if line.strip() == 'ACCOUNT NO':
            for j in range(i+4, min(i+10, len(lines))):
                val = lines[j].strip()
                # Match NNNNXX (4d+2l) or NNNNNX (5d+1l)
                if re.match(r'^\d{4,5}[A-Z]{1,2}$', val):
                    return val
    
    # Pattern 4: Scale ticket format - CUSTOMER followed by 6-digit
    match = re.search(r'CUSTOMER\s+(\d{6})', text)
    if match:
        return match.group(1)
    
    # Pattern 5: ACCOUNT NO inline with various formats
    match = re.search(r'ACCOUNT\s*NO\.?\s*[:\n\\n]?\s*(\d{4,5}[A-Z]{1,2})', text, re.I)
    if match:
        return match.group(1)
    
    # Pattern 6: Look for standalone NNNNXX or NNNNNX format
    match = re.search(r'(\d{4,5}[A-Z]{1,2})', text)
    if match:
        return match.group(1)
    
    return None


def _extract_zarc_recycling(text: str) -> Optional[str]:
    """
    ZARC Recycling - Format: NNN (3-digit)
    Examples: 979, 992
    Pattern: Customer ID: inline
    """
    match = re.search(r'Customer\s*ID:\s*(\d{3})\b', text, re.I)
    if match:
        return match.group(1)
    
    return None


def _extract_1800_got_junk(text: str) -> Optional[str]:
    """
    1-800-Got-Junk - Format: NNN (3-digit)
    Examples: 990
    Pattern: Customer ID: - columnar OCR with variable positions
    """
    lines = text.split('\\n')
    
    # Pattern 1: Find Customer ID: header and look for 3-digit nearby
    for i, line in enumerate(lines):
        if 'Customer ID:' in line:
            # Look backwards (original format)
            for j in range(max(0, i-10), i):
                val = lines[j].strip()
                if re.match(r'^\d{3}$', val):
                    return val
            # Look forwards (alternate format)
            for j in range(i+1, min(i+12, len(lines))):
                val = lines[j].strip()
                if re.match(r'^\d{3}$', val):
                    return val
    
    # Pattern 2: Customer ID: followed by value inline
    match = re.search(r'Customer\s*ID:\s*(\d{3})', text, re.I)
    if match:
        return match.group(1)
    
    return None


def _extract_ryland_environmental(text: str) -> Optional[str]:
    """
    Ryland Environmental - Multiple formats:
    - AANNNN (2 letters + 4 digits) e.g., AC4946
    - NNNNNN (6 digits) e.g., 013100
    Pattern: CUSTOMER NO inline or columnar
    Note: Skip "Transaction Receipt" documents (no account)
    """
    # Filter out transaction receipts
    if 'Transaction Receipt' in text:
        return None
    
    lines = text.split('\\n')
    
    # Pattern 1: CUSTOMER NO header with value 3 lines below (columnar)
    for i, line in enumerate(lines):
        if line.strip() == 'CUSTOMER NO':
            for j in range(i+2, min(i+6, len(lines))):
                val = lines[j].strip()
                # Match 2 letters + 4 digits OR 6 digits
                if re.match(r'^[A-Z]{2}\d{4}$', val):
                    return val
                if re.match(r'^\d{6}$', val):
                    return val
    
    # Pattern 2: CUSTOMER NO inline with value
    match = re.search(r'CUSTOMER\s*NO\.?\s+([A-Z]{2}\d{4}|\d{6})', text, re.I)
    if match:
        return match.group(1).upper() if match.group(1)[0].isalpha() else match.group(1)
    
    # Pattern 3: Customer No inline
    match = re.search(r'Customer\s*No\.?\s+([A-Z]{2}\d{4}|\d{6})', text, re.I)
    if match:
        return match.group(1).upper() if match.group(1)[0].isalpha() else match.group(1)
    
    return None


def _extract_independent_recycling(text: str) -> Optional[str]:
    """
    Independent Recycling - Format: NNNN (4-digit)
    Examples: 5905
    Pattern: CUSTOMER NO. inline
    """
    # Pattern 1: CUSTOMER NO. inline
    match = re.search(r'CUSTOMER\s*NO\.?\s*[:\n\\n]?\s*(\d{4})\b', text, re.I)
    if match:
        return match.group(1)
    
    # Pattern 2: Look in columnar format
    lines = text.split('\\n')
    for i, line in enumerate(lines):
        if 'CUSTOMER NO' in line.upper():
            for j in range(i+1, min(i+5, len(lines))):
                val = lines[j].strip()
                if re.match(r'^\d{4}$', val):
                    return val
    
    return None


def _extract_moore_coal(text: str) -> Optional[str]:
    """
    Moore Coal - Format: NNNN (4-digit)
    Examples: 4808
    Pattern: CUSTOMER NO. inline
    """
    # Pattern 1: CUSTOMER NO. inline
    match = re.search(r'CUSTOMER\s*NO\.?\s*[:\n\\n]?\s*(\d{4})\b', text, re.I)
    if match:
        return match.group(1)
    
    # Pattern 2: Look in columnar format
    lines = text.split('\\n')
    for i, line in enumerate(lines):
        if 'CUSTOMER NO' in line.upper():
            for j in range(i+1, min(i+5, len(lines))):
                val = lines[j].strip()
                if re.match(r'^\d{4}$', val):
                    return val
    
    return None


def _extract_honolulu_disposal(text: str) -> Optional[str]:
    """
    Honolulu Disposal - Format: NNNNNNNN to NNNNNNNNNN (8-10 digit)
    Examples: 2131885000, 242876300, 26254001
    Pattern: ACCOUNT or ACCT # inline
    Note: Skip holiday notices (no account)
    """
    # Filter out holiday notices
    if 'Holiday' in text and 'Collection' in text:
        return None
    
    lines = text.split('\\n')
    
    # Pattern 1: Look for 8-10 digit number after ACCOUNT header in columnar format
    for i, line in enumerate(lines):
        if line.strip() == 'ACCOUNT':
            for j in range(i+1, min(i+15, len(lines))):
                val = lines[j].strip()
                if re.match(r'^\d{8,10}$', val):
                    return val
    
    # Pattern 2: ACCT #: inline
    match = re.search(r'ACCT\s*#:\s*(\d{8,10})', text, re.I)
    if match:
        return match.group(1)
    
    # Pattern 3: ACCOUNT inline
    match = re.search(r'ACCOUNT\s*[:\n\\n]?\s*(\d{8,10})', text, re.I)
    if match:
        return match.group(1)
    
    # Pattern 4: Look for standalone 8-10 digit number that appears twice (account pattern)
    matches = re.findall(r'(\d{8,10})', text)
    from collections import Counter
    counts = Counter(matches)
    for num, count in counts.most_common():
        if count >= 2 and not num.startswith('0603'):  # Skip barcode numbers
            return num
    
    return None


def _extract_pelican_waste(text: str) -> Optional[str]:
    """
    Pelican Waste - Format: NNNNNN (6-digit)
    Examples: 031803, 026634
    Pattern: Customer No. - values on next line space-separated
    """
    lines = text.split('\\n')
    
    # Pattern 1: "Customer No. Invoice Date Invoice No. Due Date" header
    # followed by values on next line
    for i, line in enumerate(lines):
        if 'Customer No.' in line and 'Invoice' in line:
            # Next line has the values separated by spaces
            if i + 1 < len(lines):
                next_line = lines[i + 1].strip()
                # First 6 digits should be the customer number
                match = re.match(r'^(\d{6})\s', next_line)
                if match:
                    return match.group(1)
    
    # Pattern 2: Customer No. inline
    match = re.search(r'Customer\s*No\.?\s*[:\n\\n]?\s*(\d{6})', text, re.I)
    if match:
        return match.group(1)
    
    # Pattern 3: Look in columnar header format
    for i, line in enumerate(lines):
        if 'Customer No' in line:
            # Check if value is on same line
            m = re.search(r'Customer\s*No\.?\s+(\d{6})', line)
            if m:
                return m.group(1)
            for j in range(i+1, min(i+5, len(lines))):
                val = lines[j].strip()
                if re.match(r'^\d{6}$', val):
                    return val
    
    return None


# V5 Vendor Registrations - Tranche 2
VENDOR_ACCOUNTS['ABC Waste'] = {
    'has_account': True,
    'format': 'NN-NNNNN N / NN-NNNNNNN',
    'examples': ['10-339800 4', '10-3471256'],
    'extract': _extract_abc_waste
}

VENDOR_ACCOUNTS['Smith Creek'] = {
    'has_account': True,
    'format': 'WASTNNN',
    'examples': ['WAST0004'],
    'extract': _extract_smith_creek
}

VENDOR_ACCOUNTS['JLT Trucking'] = {
    'has_account': True,
    'format': 'NNNNNNN',
    'examples': ['1001434'],
    'extract': _extract_jlt_trucking
}

VENDOR_ACCOUNTS['Liberty Disposal'] = {
    'has_account': True,
    'format': 'NNNNXX / NNNNNX / NNNN / NNNNNN / NNNNNNNNNNNN',
    'examples': ['2476TU', '15990C', '1599', '019022', '731810015990'],
    'extract': _extract_liberty_disposal
}

VENDOR_ACCOUNTS['ZARC Recycling'] = {
    'has_account': True,
    'format': 'NNN',
    'examples': ['979', '992'],
    'extract': _extract_zarc_recycling
}

VENDOR_ACCOUNTS['1-800-Got-Junk'] = {
    'has_account': True,
    'format': 'NNN',
    'examples': ['990'],
    'extract': _extract_1800_got_junk
}

VENDOR_ACCOUNTS['Ryland Environmental'] = {
    'has_account': True,
    'format': 'AANNNN / NNNNNN (2L+4D or 6D)',
    'examples': ['AC4946', '013100'],
    'extract': _extract_ryland_environmental,
    'notes': 'Transaction Receipts return None (no account)'
}

VENDOR_ACCOUNTS['Independent Recycling'] = {
    'has_account': True,
    'format': 'NNNN',
    'examples': ['5905'],
    'extract': _extract_independent_recycling
}

VENDOR_ACCOUNTS['Moore Coal'] = {
    'has_account': True,
    'format': 'NNNN',
    'examples': ['4808'],
    'extract': _extract_moore_coal
}

VENDOR_ACCOUNTS['Honolulu Disposal'] = {
    'has_account': True,
    'format': 'NNNNNNNN to NNNNNNNNNN (8-10 digit)',
    'examples': ['2131885000', '242876300', '26254001'],
    'extract': _extract_honolulu_disposal
}

VENDOR_ACCOUNTS['Pelican Waste'] = {
    'has_account': True,
    'format': 'NNNNNN',
    'examples': ['031803', '026634'],
    'extract': _extract_pelican_waste
}


# ============================================================
# V6 ADDITIONS - Account Linkage Project (January 2026)
# ============================================================

def _extract_amwaste(text: str) -> Optional[str]:
    """Format: 6-digit after ACCOUNT #:
    Examples: 023895, 024172, 106870
    """
    match = re.search(r'ACCOUNT\s*#:?\s*(\d{6})', text, re.IGNORECASE)
    return match.group(1) if match else None

VENDOR_ACCOUNTS['Amwaste'] = {
    'has_account': True,
    'format': 'NNNNNN',
    'examples': ['023895', '024172', '106870'],
    'extract': _extract_amwaste
}


def _extract_ssf_scavenger(text: str) -> Optional[str]:
    """Format: 6-digit - appears after header row (Account No, Account Name, Invoice Date, Invoice No)
    The account number is the first 6-digit value after Invoice No. header
    Examples: 027018
    """
    # Format: Account No.\nAccount Name\nInvoice Date\nInvoice No.\n027018
    match = re.search(r'Account\s*No\.?\\nAccount\s*Name\\nInvoice\s*Date\\nInvoice\s*No\.?\\n(\d{6})', text, re.IGNORECASE)
    if match:
        return match.group(1)
    # Fallback: find first 6-digit number after "Account No." header
    match = re.search(r'Account\s*No\.?.*?\\n(\d{6})', text, re.IGNORECASE)
    return match.group(1) if match else None

VENDOR_ACCOUNTS['South San Francisco Scavenger'] = {
    'has_account': True,
    'format': 'NNNNNN',
    'examples': ['027018'],
    'extract': _extract_ssf_scavenger
}


def _extract_a1_porta_potty(text: str) -> Optional[str]:
    """Format: Alphanumeric Customer ID (e.g., C4856)
    Examples: C4856
    """
    match = re.search(r'Customer\s*ID\s*[:\s]*([A-Z]\d{4,6})', text, re.IGNORECASE)
    return match.group(1).upper() if match else None

VENDOR_ACCOUNTS['A1 Porta Potty'] = {
    'has_account': True,
    'format': 'ANNNN',
    'examples': ['C4856'],
    'extract': _extract_a1_porta_potty
}


def _extract_marpan_supply(text: str) -> Optional[str]:
    """Format: 6-digit after CUSTOMER NO. (may be on next line)
    Examples: 011411
    """
    # Try same line first
    match = re.search(r'CUSTOMER\s*NO\.?\s*(\d{6})', text, re.IGNORECASE)
    if match:
        return match.group(1)
    # Try next line (\\n is literal in OCR text)
    match = re.search(r'CUSTOMER\s*NO\.?\\n(\d{6})', text, re.IGNORECASE)
    return match.group(1) if match else None

VENDOR_ACCOUNTS['Marpan Supply'] = {
    'has_account': True,
    'format': 'NNNNNN',
    'examples': ['011411'],
    'extract': _extract_marpan_supply
}


def _extract_cc_disposal(text: str) -> Optional[str]:
    """Format: 4-digit after Account Number -
    Examples: 1710
    """
    match = re.search(r'Account\s*Number\s*[-:]\s*(\d{4})', text, re.IGNORECASE)
    return match.group(1) if match else None

VENDOR_ACCOUNTS['C&C Disposal'] = {
    'has_account': True,
    'format': 'NNNN',
    'examples': ['1710'],
    'extract': _extract_cc_disposal
}


# ============================================================
# V6 ADDITIONS - Account Linkage Project (January 2026)
# ============================================================

def _extract_empire_waste(text: str) -> Optional[str]:
    """Empire Waste - NavuSoft format
    Format: 4-digit after ACCOUNT #
    Examples: 1930, 2714
    """
    lines = text.replace('\\n', '\n').split('\n')

    # Pattern 1: After ACCOUNT # header in NavuSoft format
    for i, line in enumerate(lines[:20]):
        if 'ACCOUNT #' in line.upper():
            match = re.search(r'ACCOUNT\s*#:?\s*(\d{4})\b', line, re.I)
            if match:
                return match.group(1)
            # Check next few lines
            for j in range(i+1, min(i+5, len(lines))):
                val = lines[j].strip()
                if re.match(r'^\d{4}$', val):
                    return val
    return None

VENDOR_ACCOUNTS['Empire Waste'] = {
    'has_account': True,
    'format': 'NNNN',
    'examples': ['1930', '2714'],
    'extract': _extract_empire_waste
}


def _extract_walters_recycling(text: str) -> Optional[str]:
    """Walters Recycling & Refuse
    Format: 6-digit CUSTOMER ID (may be on next line)
    Examples: 249292, 249297
    """
    # Pattern 1: Same line
    match = re.search(r'CUSTOMER\s*ID[:\s]*(\d{6})', text, re.I)
    if match:
        return match.group(1)

    # Pattern 2: Next line after CUSTOMER ID
    lines = text.replace('\\n', '\n').split('\n')
    for i, line in enumerate(lines):
        if 'CUSTOMER ID' in line.upper():
            # Check next few lines for 6-digit number
            for j in range(i+1, min(i+4, len(lines))):
                val = lines[j].strip()
                if re.match(r'^\d{6}$', val):
                    return val
    return None

VENDOR_ACCOUNTS['Walters Recycling'] = {
    'has_account': True,
    'format': 'NNNNNN',
    'examples': ['249292', '249297', '249296'],
    'extract': _extract_walters_recycling
}


def _extract_nexus_disposal(text: str) -> Optional[str]:
    """Nexus Disposal
    Format: NNNNN-NNN (5 digits, dash, 3 digits)
    Examples: 23736-007, 23736-005
    """
    match = re.search(r'ACCOUNT[:\s]+(\d{5}-\d{3})', text, re.I)
    return match.group(1) if match else None

VENDOR_ACCOUNTS['Nexus Disposal'] = {
    'has_account': True,
    'format': 'NNNNN-NNN',
    'examples': ['23736-007', '23736-005', '23736-026'],
    'extract': _extract_nexus_disposal
}


def _extract_all_american_waste(text: str) -> Optional[str]:
    """All American Waste
    Format: 6-digit after ACCOUNT #
    Examples: 205127, 207498
    """
    match = re.search(r'ACCOUNT\s*#[:\s]*(\d{6})', text, re.I)
    return match.group(1) if match else None

VENDOR_ACCOUNTS['All American Waste'] = {
    'has_account': True,
    'format': 'NNNNNN',
    'examples': ['205127', '207498', '226822'],
    'extract': _extract_all_american_waste
}


def _extract_troiano_waste(text: str) -> Optional[str]:
    """Troiano Waste Services
    Format: 6-digit after CUSTOMER NO (may have OL prefix on next line)
    Examples: 022308, 020843
    """
    # Pattern 1: Same line
    match = re.search(r'CUSTOMER\s*NO[:\s]*(\d{6})', text, re.I)
    if match:
        return match.group(1)

    # Pattern 2: Next lines after CUSTOMER NO (may have OL prefix)
    lines = text.replace('\\n', '\n').split('\n')
    for i, line in enumerate(lines):
        if 'CUSTOMER NO' in line.upper():
            # Check next few lines for 6-digit number
            for j in range(i+1, min(i+4, len(lines))):
                val = lines[j].strip()
                if re.match(r'^\d{6}$', val):
                    return val
    return None

VENDOR_ACCOUNTS['Troiano Waste'] = {
    'has_account': True,
    'format': 'NNNNNN',
    'examples': ['022308', '020843'],
    'extract': _extract_troiano_waste
}


def _extract_usa_waste(text: str) -> Optional[str]:
    """USA Waste & Recycling
    Format: 6-digit after ACCOUNT #
    Examples: 205127, 226822
    """
    match = re.search(r'ACCOUNT\s*#[:\s]*(\d{6})', text, re.I)
    return match.group(1) if match else None

VENDOR_ACCOUNTS['USA Waste'] = {
    'has_account': True,
    'format': 'NNNNNN',
    'examples': ['205127', '226822', '207498'],
    'extract': _extract_usa_waste
}


def _extract_arrowaste(text: str) -> Optional[str]:
    """Arrowaste
    Format: NN-NNNNN N (2 digits, dash, 5 digits, space, check digit)
    Examples: 91-99545 6, 91-99544 9
    Note: Uses Casella-style check digit format
    """
    match = re.search(r'Cust\.?\s*#[:\s]*(\d{2}-\d{5}\s*\d)', text, re.I)
    if match:
        return match.group(1).strip()
    return None

VENDOR_ACCOUNTS['Arrowaste'] = {
    'has_account': True,
    'format': 'NN-NNNNN N',
    'examples': ['91-99545 6', '91-99544 9', '91-53681 3'],
    'extract': _extract_arrowaste
}


def _extract_delta_waste(text: str) -> Optional[str]:
    """Delta Waste Solutions - NavuSoft format
    Format: 4-digit - NavuSoft has values BEFORE labels in columnar layout
    Examples: 1014
    """
    lines = text.replace('\\n', '\n').split('\n')

    # NavuSoft pattern: values come BEFORE the ACCOUNT # label
    # Find ACCOUNT # and look at preceding lines
    for i, line in enumerate(lines[:20]):
        if 'ACCOUNT #' in line.upper():
            # Check preceding lines for 4-digit value
            for j in range(i-1, max(i-5, -1), -1):
                val = lines[j].strip()
                if re.match(r'^\d{4}$', val):
                    return val

    # Fallback: search for 4-digit after ACCOUNT #
    match = re.search(r'ACCOUNT\s*#:?\s*(\d{4})\b', text, re.I)
    if match:
        return match.group(1)
    return None

VENDOR_ACCOUNTS['Delta Waste'] = {
    'has_account': True,
    'format': 'NNNN',
    'examples': ['1014'],
    'extract': _extract_delta_waste
}


# ============================================================================
# V6 BATCH 2 - Account Linkage Gap Closure
# ============================================================================

def _extract_harters(text: str) -> Optional[str]:
    """Harter's - Multiple formats across divisions
    Format 1: 6-digit (Quick Clean Up) - 023912
    Format 2: NN-NNNNN N (Fox Valley/Lakeside) - 01-82270 9, 02-45868 5
    """
    # Pattern 1: Customer # with district format (NN-NNNNN N)
    match = re.search(r'Customer\s*#:?\s*(\d{2}-\d{5}\s*\d)', text, re.I)
    if match:
        return match.group(1)

    # Pattern 2: Customer Nbr with 6-digit
    match = re.search(r'Customer\s+Nbr[:\s]*(\d{6})\b', text, re.I)
    if match:
        return match.group(1)

    # Pattern 3: Columnar - label on one line, value on next
    lines = text.replace('\\n', '\n').split('\n')
    for i, line in enumerate(lines[:-1]):
        if 'customer' in line.lower() and ('#' in line or 'nbr' in line.lower()):
            val = lines[i+1].strip()
            # 6-digit format
            if re.match(r'^\d{6}$', val):
                return val
            # District format
            m = re.match(r'^(\d{2}-\d{5}\s*\d)$', val)
            if m:
                return m.group(1)

    return None

VENDOR_ACCOUNTS["Harter's"] = {
    'has_account': True,
    'format': 'NNNNNN or NN-NNNNN N',
    'examples': ['023912', '01-82270 9'],
    'extract': _extract_harters
}


def _extract_cockeys(text: str) -> Optional[str]:
    """Cockey's Enterprises - Site-level account extraction.
    Returns full site account (NNNNNNN or NNNNN-NNN joined).
    Falls back to 5-digit master account if no site suffix found.
    Examples: Site 10490006 -> 10490006, ACCOUNT # 10490-022 -> 10490022
    """
    lines = text.replace('\\n', '\n').split('\n')

    # Pattern 1: "Site NNNNNNN" (old invoice format)
    m = re.search(r'\bSite\s+(\d{7,8})\b', text)
    if m:
        return m.group(1)

    # Pattern 2: "ACCOUNT # NNNNN-NNN" — return joined digits
    for i, line in enumerate(lines):
        if 'ACCOUNT #' in line.upper():
            # Inline: "ACCOUNT # 10490-022"
            m = re.search(r'ACCOUNT\s*#:?\s*(\d{5})-(\d{3})', line, re.I)
            if m:
                return m.group(1) + m.group(2)
            # Next lines
            for j in range(i+1, min(i+6, len(lines))):
                val = lines[j].strip()
                m = re.match(r'^(\d{5})-(\d{3})$', val)
                if m:
                    return m.group(1) + m.group(2)

    # Pattern 3: Fallback — 5-digit master account
    for i, line in enumerate(lines):
        if 'ACCOUNT #' in line.upper():
            for j in range(i+1, min(i+6, len(lines))):
                val = lines[j].strip()
                if re.match(r'^(\d{5})$', val):
                    return val
    match = re.search(r'ACCOUNT\s*#:?\s*(\d{5})\b', text, re.I)
    if match:
        return match.group(1)
    return None

VENDOR_ACCOUNTS["Cockey's Enterprises"] = {
    'has_account': True,
    'format': 'NNNNNNN',
    'examples': ['10490006', '10490022'],
    'extract': _extract_cockeys
}


def _extract_liberty_waste(text: str) -> Optional[str]:
    """Liberty Waste - Casella-style check digit format
    Format: NN-NNNNN N (district-account check_digit)
    Examples: 09-45904 1, 01-65373 2
    """
    # Pattern 1: Account No. label
    match = re.search(r'Account\s*No\.?\s*(\d{2}-\d{5}\s*\d)', text, re.I)
    if match:
        return match.group(1).strip()

    # Pattern 2: Customer # label
    match = re.search(r'Customer\s*#[:\s]*(\d{2}-\d{5}\s*\d)', text, re.I)
    if match:
        return match.group(1).strip()

    return None

VENDOR_ACCOUNTS['Liberty Waste'] = {
    'has_account': True,
    'format': 'NN-NNNNN N',
    'examples': ['09-45904 1', '01-65373 2'],
    'extract': _extract_liberty_waste
}


# ============================================================
# NEW VENDORS - JANUARY 2026 BATCH (Automated Analysis)
# ============================================================

def _extract_gateway_disposal_account(text: str) -> Optional[str]:
    """Format: NNNNNN (6-digit after ACCOUNT#)
    Examples: 718227
    """
    match = re.search(r'ACCOUNT#\s*\\n(\d{6})', text, re.I)
    if match:
        return match.group(1).strip()
    # Fallback: inline format
    match = re.search(r'ACCOUNT#\s*(\d{6})', text, re.I)
    if match:
        return match.group(1)
    return None

VENDOR_ACCOUNTS['Gateway Disposal'] = {
    'has_account': True,
    'format': 'NNNNNN',
    'examples': ['718227', '777815'],
    'extract': _extract_gateway_disposal_account
}


def _extract_wg_waste_account(text: str) -> Optional[str]:
    """Format: NNNNNN (6-digit after ACCOUNT#)
    Examples: 100327
    """
    match = re.search(r'ACCOUNT#\s*\\n(\d{6})', text, re.I)
    if match:
        return match.group(1).strip()
    match = re.search(r'ACCOUNT#\s*(\d{6})', text, re.I)
    if match:
        return match.group(1)
    return None

VENDOR_ACCOUNTS['WG Waste'] = {
    'has_account': True,
    'format': 'NNNNNN',
    'examples': ['100327'],
    'extract': _extract_wg_waste_account
}


def _extract_waste_away_account(text: str) -> Optional[str]:
    """Himco Waste-Away Service - Format: NNNNNN (6-digit)
    Examples: 255775
    """
    match = re.search(r'Account\s*#\s*\\n?(\d{6})', text, re.I)
    if match:
        return match.group(1).strip()
    match = re.search(r'Account\s*#\s*(\d{6})', text, re.I)
    if match:
        return match.group(1)
    return None

VENDOR_ACCOUNTS['Waste Away'] = {
    'has_account': True,
    'format': 'NNNNNN',
    'examples': ['255775'],
    'extract': _extract_waste_away_account
}


def _extract_blue_hills_environmental_account(text: str) -> Optional[str]:
    """Format: NNNNNN (AccountNumber in footer)
    Examples: 112833
    """
    match = re.search(r'AccountNumber:\s*(\d{6})', text, re.I)
    if match:
        return match.group(1)
    match = re.search(r'Account\s*Number[:\s]*(\d{6})', text, re.I)
    if match:
        return match.group(1)
    return None

VENDOR_ACCOUNTS['Blue Hills Environmental'] = {
    'has_account': True,
    'format': 'NNNNNN',
    'examples': ['112833'],
    'extract': _extract_blue_hills_environmental_account
}


def _extract_trident_waste_account(text: str) -> Optional[str]:
    """Format: NN-NNNNN N (Account No.)
    Examples: 01-29051 9
    """
    match = re.search(r'Account\s*No\.?\s*(\d{2}-\d{5}\s*\d?)', text, re.I)
    if match:
        return match.group(1).strip()
    return None

VENDOR_ACCOUNTS['Trident Waste'] = {
    'has_account': True,
    'format': 'NN-NNNNN N',
    'examples': ['01-29051 9'],
    'extract': _extract_trident_waste_account
}


def _extract_west_central_sanitation_account(text: str) -> Optional[str]:
    """Format: NNNNNNNN (8-digit Account Number)
    Examples: 19824400
    """
    match = re.search(r'Account\s*Number\s*\\n(\d{8})', text, re.I)
    if match:
        return match.group(1)
    match = re.search(r'Account:\s*(\d{8})', text, re.I)
    if match:
        return match.group(1)
    return None

VENDOR_ACCOUNTS['West Central Sanitation'] = {
    'has_account': True,
    'format': 'NNNNNNNN',
    'examples': ['19824400'],
    'extract': _extract_west_central_sanitation_account
}


def _extract_tk_trash_account(text: str) -> Optional[str]:
    """Trash Kans - Format: NN-NNNNNN N (Cust. #)
    Examples: 75-601875 6
    """
    match = re.search(r'Cust\.\s*#\s*\\n(\d{2}-\d{6}\s*\d)', text, re.I)
    if match:
        return match.group(1).strip()
    match = re.search(r'Cust\.\s*#\s*(\d{2}-\d{6}\s*\d)', text, re.I)
    if match:
        return match.group(1).strip()
    return None

VENDOR_ACCOUNTS['TK Trash'] = {
    'has_account': True,
    'format': 'NN-NNNNNN N',
    'examples': ['75-601875 6'],
    'extract': _extract_tk_trash_account
}


def _extract_florida_express_waste_account(text: str) -> Optional[str]:
    """Format: NN-NNNNN N (Account No.)
    Examples: 01-83825 9
    """
    match = re.search(r'Account\s*No\.?\s*(\d{2}-\d{5}\s*\d)', text, re.I)
    if match:
        return match.group(1).strip()
    return None

VENDOR_ACCOUNTS['Florida Express Waste'] = {
    'has_account': True,
    'format': 'NN-NNNNN N',
    'examples': ['01-83825 9'],
    'extract': _extract_florida_express_waste_account
}


def _extract_abc_disposal_systems_account(text: str) -> Optional[str]:
    """Format: NN-NNNNNN N (Account No.)
    Examples: 01-169971 8
    """
    match = re.search(r'Account\s*No\.?\s*(\d{2}-\d{6}\s*\d)', text, re.I)
    if match:
        return match.group(1).strip()
    return None

VENDOR_ACCOUNTS['ABC Disposal Systems'] = {
    'has_account': True,
    'format': 'NN-NNNNNN N',
    'examples': ['01-169971 8'],
    'extract': _extract_abc_disposal_systems_account
}


def _extract_dekalb_county_account(text: str) -> Optional[str]:
    """Format: NNNNNNNNNN (10-digit Account Number)
    Examples: 6007916600
    """
    match = re.search(r'Account\s*Number\s*\\n(\d{10})', text, re.I)
    if match:
        return match.group(1)
    match = re.search(r'Account\s*Number\s*(\d{10})', text, re.I)
    if match:
        return match.group(1)
    return None

VENDOR_ACCOUNTS['DeKalb County'] = {
    'has_account': True,
    'format': 'NNNNNNNNNN',
    'examples': ['6007916600'],
    'extract': _extract_dekalb_county_account
}


def _extract_jk_trash_account(text: str) -> Optional[str]:
    """J&K Trash - Format: NNNNNN (6-digit ACCOUNT#)
    Examples: 585080
    """
    match = re.search(r'ACCOUNT#\s*\\n(\d{6})', text, re.I)
    if match:
        return match.group(1)
    match = re.search(r'ACCOUNT#\s*(\d{6})', text, re.I)
    if match:
        return match.group(1)
    return None

VENDOR_ACCOUNTS['J&K Trash'] = {
    'has_account': True,
    'format': 'NNNNNN',
    'examples': ['585080'],
    'extract': _extract_jk_trash_account
}


def _extract_cards_recycling_account(text: str) -> Optional[str]:
    """Format: NN-NNNNN N (Account No.)
    Examples: 20-32943 1
    """
    match = re.search(r'Account\s*No\.?\s*(\d{2}-\d{5}\s*\d)', text, re.I)
    if match:
        return match.group(1).strip()
    return None

VENDOR_ACCOUNTS['Cards Recycling'] = {
    'has_account': True,
    'format': 'NN-NNNNN N',
    'examples': ['20-32943 1'],
    'extract': _extract_cards_recycling_account
}


def _extract_heiberg_garbage_account(text: str) -> Optional[str]:
    """Format: NNNNNN (6-digit Account Number)
    Examples: 137851
    """
    match = re.search(r'Account\s*Number\s*(\d{6})', text, re.I)
    if match:
        return match.group(1)
    return None

VENDOR_ACCOUNTS['Heiberg Garbage'] = {
    'has_account': True,
    'format': 'NNNNNN',
    'examples': ['137851'],
    'extract': _extract_heiberg_garbage_account
}


def _extract_black_hawk_waste_account(text: str) -> Optional[str]:
    """Format: NN-NNNNNN (Account No.)
    Examples: 04-333894
    """
    match = re.search(r'Account\s*No\.?\s*(\d{2}-\d{6})', text, re.I)
    if match:
        return match.group(1)
    return None

VENDOR_ACCOUNTS['Black Hawk Waste'] = {
    'has_account': True,
    'format': 'NN-NNNNNN',
    'examples': ['04-333894'],
    'extract': _extract_black_hawk_waste_account
}


def _extract_wall_recycling_account(text: str) -> Optional[str]:
    """Format: NN-NNNNN N (Account No.)
    Examples: 01-61716 6
    """
    match = re.search(r'Account\s*No\.?\s*(\d{2}-\d{5}\s*\d)', text, re.I)
    if match:
        return match.group(1).strip()
    return None

VENDOR_ACCOUNTS['Wall Recycling'] = {
    'has_account': True,
    'format': 'NN-NNNNN N',
    'examples': ['01-61716 6'],
    'extract': _extract_wall_recycling_account
}


def _extract_western_elite_account(text: str) -> Optional[str]:
    """Format: NNNNNNNN (8-digit Account Number)
    Examples: 12030803
    """
    match = re.search(r'Account\s*Number[:\s]*(\d{8})', text, re.I)
    if match:
        return match.group(1)
    return None

VENDOR_ACCOUNTS['Western Elite'] = {
    'has_account': True,
    'format': 'NNNNNNNN',
    'examples': ['12030803'],
    'extract': _extract_western_elite_account
}


def _extract_orlando_waste_paper_account(text: str) -> Optional[str]:
    """Format: NNNNNN (6-digit ACCOUNT#)
    Examples: 902765
    """
    match = re.search(r'ACCOUNT#\s*\\n(\d{6})', text, re.I)
    if match:
        return match.group(1)
    match = re.search(r'ACCOUNT#\s*(\d{6})', text, re.I)
    if match:
        return match.group(1)
    return None

VENDOR_ACCOUNTS['Orlando Waste Paper'] = {
    'has_account': True,
    'format': 'NNNNNN',
    'examples': ['902765'],
    'extract': _extract_orlando_waste_paper_account
}


def _extract_county_waste_systems_account(text: str) -> Optional[str]:
    """Format: NN-NNNNN N (Account No.)
    Examples: 07-44243 7
    """
    match = re.search(r'Account\s*No\.?\s*(\d{2}-\d{5}\s*\d)', text, re.I)
    if match:
        return match.group(1).strip()
    return None

VENDOR_ACCOUNTS['County Waste Systems'] = {
    'has_account': True,
    'format': 'NN-NNNNN N',
    'examples': ['07-44243 7'],
    'extract': _extract_county_waste_systems_account
}


def _extract_sonnys_solid_waste_account(text: str) -> Optional[str]:
    """Sonny's Solid Waste - Format: NNNNN (5-digit Acct #)
    Examples: 16645
    """
    match = re.search(r'Acct\s*#\s*(\d{5})', text, re.I)
    if match:
        return match.group(1)
    return None

VENDOR_ACCOUNTS["Sonny's Solid Waste"] = {
    'has_account': True,
    'format': 'NNNNN',
    'examples': ['16645'],
    'extract': _extract_sonnys_solid_waste_account
}


def _extract_indiana_waste_account(text: str) -> Optional[str]:
    """Format: NNNNNN (6-digit ACCOUNT#)
    Examples: 443296
    """
    match = re.search(r'ACCOUNT#\s*\\n(\d{6})', text, re.I)
    if match:
        return match.group(1)
    match = re.search(r'ACCOUNT#\s*(\d{6})', text, re.I)
    if match:
        return match.group(1)
    return None

VENDOR_ACCOUNTS['Indiana Waste'] = {
    'has_account': True,
    'format': 'NNNNNN',
    'examples': ['443296'],
    'extract': _extract_indiana_waste_account
}


def _extract_west_oahu_aggregate_account(text: str) -> Optional[str]:
    """Format: NNNNNNN (7-digit Account Number)
    Examples: 1970107
    """
    match = re.search(r'Account\s*Number[:\s]*(\d{7})', text, re.I)
    if match:
        return match.group(1)
    return None

VENDOR_ACCOUNTS['West Oahu Aggregate'] = {
    'has_account': True,
    'format': 'NNNNNNN',
    'examples': ['1970107'],
    'extract': _extract_west_oahu_aggregate_account
}


def _extract_northern_waste_account(text: str) -> Optional[str]:
    """Format: NNNNNN (6-digit)
    Examples: 183762
    """
    match = re.search(r'Account\s*Number[:\s]*(\d{6})', text, re.I)
    if match:
        return match.group(1)
    return None

VENDOR_ACCOUNTS['Northern Waste'] = {
    'has_account': True,
    'format': 'NNNNNN',
    'examples': ['183762'],
    'extract': _extract_northern_waste_account
}


def _extract_south_shore_disposal_account(text: str) -> Optional[str]:
    """Format: NNNNNN (6-digit)
    Examples: 102859
    """
    match = re.search(r'Account\s*Number[:\s]*(\d{6})', text, re.I)
    if match:
        return match.group(1)
    return None

VENDOR_ACCOUNTS['South Shore Disposal'] = {
    'has_account': True,
    'format': 'NNNNNN',
    'examples': ['102859'],
    'extract': _extract_south_shore_disposal_account
}


def _extract_cards_ks_account(text: str) -> Optional[str]:
    """Cards KS - Format: NN-NNNNN N (Account No.)
    Examples: 20-32943 1
    """
    match = re.search(r'Account\s*No\.?\s*(\d{2}-\d{5}\s*\d)', text, re.I)
    if match:
        return match.group(1).strip()
    return None

VENDOR_ACCOUNTS['Cards KS'] = {
    'has_account': True,
    'format': 'NN-NNNNN N',
    'examples': ['20-32943 1'],
    'extract': _extract_cards_ks_account
}


def _extract_city_of_boise_account(text: str) -> Optional[str]:
    """Format: NNNNNNNNN (9-digit Account Number)
    Examples: 105055200
    """
    match = re.search(r'Account\s*Number[:\s]*(\d{9})', text, re.I)
    if match:
        return match.group(1)
    return None

VENDOR_ACCOUNTS['City of Boise'] = {
    'has_account': True,
    'format': 'NNNNNNNNN',
    'examples': ['105055200'],
    'extract': _extract_city_of_boise_account
}


def _extract_community_waste_disposal_account(text: str) -> Optional[str]:
    """Format: NN-NNNNNN N (Customer Number)
    Examples: 10-143288 8
    """
    match = re.search(r'Customer\s*Number[:\s]*(\d{2}-\d{6}\s*\d)', text, re.I)
    if match:
        return match.group(1).strip()
    return None

VENDOR_ACCOUNTS['Community Waste Disposal'] = {
    'has_account': True,
    'format': 'NN-NNNNNN N',
    'examples': ['10-143288 8'],
    'extract': _extract_community_waste_disposal_account
}


def _extract_city_waste_account(text: str) -> Optional[str]:
    """City Waste / Coastal Compaction - Format: NN-NNNNN N (Customer #)
    Examples: 10-5845 2
    """
    match = re.search(r'Customer\s*#[:\s]*(\d{2}-\d{4,5}\s*\d)', text, re.I)
    if match:
        return match.group(1).strip()
    return None

VENDOR_ACCOUNTS['City Waste'] = {
    'has_account': True,
    'format': 'NN-NNNNN N',
    'examples': ['10-5845 2'],
    'extract': _extract_city_waste_account
}


def _extract_western_disposal_account(text: str) -> Optional[str]:
    """Format: NNNNNN (6-digit Account #)
    Examples: 123825
    Columnar format: Account # header, value several lines down
    """
    lines = text.replace('\\n', '\n').split('\n')

    # Pattern 1: Account # header, value in nearby lines
    for i, line in enumerate(lines):
        if re.match(r'^Account\s*#\s*$', line, re.I):
            for j in range(i+1, min(i+6, len(lines))):
                val = lines[j].strip()
                if re.match(r'^\d{6}$', val):
                    return val

    # Pattern 2: Inline format
    match = re.search(r'Account\s*#\s*(\d{6})', text, re.I)
    if match:
        return match.group(1)

    return None

VENDOR_ACCOUNTS['Western Disposal'] = {
    'has_account': True,
    'format': 'NNNNNN',
    'examples': ['123825'],
    'extract': _extract_western_disposal_account
}


def _extract_redgate_disposal_account(text: str) -> Optional[str]:
    """Format: XNNNN (letter prefix + 4 digits)
    Examples: C8501
    """
    match = re.search(r'Account\s*#\s*\\n([A-Z]\d{4})', text, re.I)
    if match:
        return match.group(1)
    match = re.search(r'Account\s*#\s*([A-Z]\d{4})', text, re.I)
    if match:
        return match.group(1)
    return None

VENDOR_ACCOUNTS['Redgate Disposal'] = {
    'has_account': True,
    'format': 'XNNNN',
    'examples': ['C8501'],
    'extract': _extract_redgate_disposal_account
}


def _extract_gulf_coast_containers_account(text: str) -> Optional[str]:
    """Format: NNNN (4-digit CUSTOMER NO.)
    Examples: 3401
    """
    match = re.search(r'CUSTOMER\s*NO\.?\s*\\n(\d{4})', text, re.I)
    if match:
        return match.group(1)
    return None

VENDOR_ACCOUNTS['Gulf Coast Containers'] = {
    'has_account': True,
    'format': 'NNNN',
    'examples': ['3401'],
    'extract': _extract_gulf_coast_containers_account
}


def _extract_nk_waste_account(text: str) -> Optional[str]:
    """NK Waste (Swatco) - Format: NNNNN (5-digit ACCOUNT NO)
    Examples: 01271, 42455, 59695
    Note: Multiple header lines may appear before value
    """
    lines = text.replace('\\n', '\n').split('\n')

    # Pattern 1: ACCOUNT NO header, value in nearby lines
    for i, line in enumerate(lines):
        if 'ACCOUNT NO' in line.upper() and 'NAME' not in line.upper():
            for j in range(i+1, min(i+6, len(lines))):
                val = lines[j].strip()
                if re.match(r'^\d{5}$', val):
                    return val

    # Pattern 2: Acct#: format (Hudgins)
    match = re.search(r'Acct\s*#:?\s*(\d{5})', text, re.I)
    if match:
        return match.group(1)

    return None

VENDOR_ACCOUNTS['NK Waste'] = {
    'has_account': True,
    'format': 'NNNNN',
    'examples': ['01271', '59695'],
    'extract': _extract_nk_waste_account
}


def _extract_modern_recycling_account(text: str) -> Optional[str]:
    """Modern Recycling/Modern Corporation - Format: NNNNN (5-digit Customer #)
    Examples: 68741
    """
    match = re.search(r'Customer\s*#\s*(\d{5})', text, re.I)
    if match:
        return match.group(1)
    return None

VENDOR_ACCOUNTS['Modern Recycling'] = {
    'has_account': True,
    'format': 'NNNNN',
    'examples': ['68741'],
    'extract': _extract_modern_recycling_account
}


def _extract_lexington_site_services_account(text: str) -> Optional[str]:
    """Lexington Site Services - Format: NNNNNNNNN (9-digit Account Number)
    Examples: 218734602
    """
    match = re.search(r'Account\s*Number\s*\\n(\d{9})', text, re.I)
    if match:
        return match.group(1)
    return None

VENDOR_ACCOUNTS['Lexington Site Services'] = {
    'has_account': True,
    'format': 'NNNNNNNNN',
    'examples': ['218734602'],
    'extract': _extract_lexington_site_services_account
}


def _extract_city_of_tucson_account(text: str) -> Optional[str]:
    """Format: NNNNNNN-NNNNNN (Account Number)
    Examples: 1679429-206512
    """
    match = re.search(r'ACCOUNT\s*NUMBER\s*\\n(\d{7}-\d{6})', text, re.I)
    if match:
        return match.group(1)
    match = re.search(r'Account\s*Number\s*(\d{7}-\d{6})', text, re.I)
    if match:
        return match.group(1)
    return None

VENDOR_ACCOUNTS['City of Tucson'] = {
    'has_account': True,
    'format': 'NNNNNNN-NNNNNN',
    'examples': ['1679429-206512'],
    'extract': _extract_city_of_tucson_account
}


def _extract_ohio_valley_waste_account(text: str) -> Optional[str]:
    """Format: NN NNNNNNN N (Customer Number with spaces)
    Examples: 90 0005772 0
    """
    match = re.search(r'Customer\s*Number[:\s]*(\d{2}\s*\d{7}\s*\d)', text, re.I)
    if match:
        return match.group(1)
    return None

VENDOR_ACCOUNTS['Ohio Valley Waste'] = {
    'has_account': True,
    'format': 'NN NNNNNNN N',
    'examples': ['90 0005772 0'],
    'extract': _extract_ohio_valley_waste_account
}


def _extract_vogel_disposal_account(text: str) -> Optional[str]:
    """Format: NN NNNNNNN N (Customer Number with spaces)
    Examples: 01 0027156 8
    """
    match = re.search(r'Customer\s*Number[:\s]*(\d{2}\s*\d{7}\s*\d)', text, re.I)
    if match:
        return match.group(1)
    return None

VENDOR_ACCOUNTS['Vogel Disposal'] = {
    'has_account': True,
    'format': 'NN NNNNNNN N',
    'examples': ['01 0027156 8'],
    'extract': _extract_vogel_disposal_account
}


# ============================================================
# V8 AUTO-GENERATED EXTRACTORS - January 2026
# 113 vendors with auto-detected account patterns from OCR analysis
# ============================================================

def _extract_kahut_waste_account(text: str) -> Optional[str]:
    """Format: NNNN-NNNNNNNN - Example: 2021-71937218"""
    match = re.search(r'(?:Account|Acct)\s*#:?\s*(\d{4}-\d{8})', text, re.I)
    return match.group(1) if match else None

VENDOR_ACCOUNTS['Kahut Waste'] = {
    'has_account': True,
    'format': 'NNNN-NNNNNNNN',
    'examples': ['2021-71937218'],
    'extract': _extract_kahut_waste_account
}

def _extract_sonnys_solid_waste_account(text: str) -> Optional[str]:
    """Format: NNNNN - Example: 16645"""
    match = re.search(r'(?:Account|Acct)\s*#:?\s*(\d{4,6})', text, re.I)
    return match.group(1) if match else None

VENDOR_ACCOUNTS["Sonny's Solid Waste"] = {
    'has_account': True,
    'format': 'NNNNN',
    'examples': ['16645'],
    'extract': _extract_sonnys_solid_waste_account
}

def _extract_grace_hauling_account(text: str) -> Optional[str]:
    """Format: NNNNNNN - Example: 2900585"""
    match = re.search(r'(?:Account|Acct)\s*#:?\s*(\d{6,8})', text, re.I)
    return match.group(1) if match else None

VENDOR_ACCOUNTS['Grace Hauling'] = {
    'has_account': True,
    'format': 'NNNNNNN',
    'examples': ['2900585'],
    'extract': _extract_grace_hauling_account
}

def _extract_pacific_waste_account(text: str) -> Optional[str]:
    """Format: NNNNNN - Example: 082698"""
    match = re.search(r'(?:Account|Acct)\s*#:?\s*(\d{5,7})', text, re.I)
    return match.group(1) if match else None

VENDOR_ACCOUNTS['Pacific Waste'] = {
    'has_account': True,
    'format': 'NNNNNN',
    'examples': ['082698'],
    'extract': _extract_pacific_waste_account
}

def _extract_cavossa_disposal_account(text: str) -> Optional[str]:
    """Format: NNNNNN - Example: 133508"""
    match = re.search(r'(?:Account|Acct)\s*#:?\s*(\d{5,7})', text, re.I)
    return match.group(1) if match else None

VENDOR_ACCOUNTS['Cavossa Disposal'] = {
    'has_account': True,
    'format': 'NNNNNN',
    'examples': ['133508'],
    'extract': _extract_cavossa_disposal_account
}

def _extract_burgmeiers_hauling_account(text: str) -> Optional[str]:
    """Format: NNNNNNN - Example: 1537213"""
    match = re.search(r'(?:Account|Acct)\s*#:?\s*(\d{6,8})', text, re.I)
    return match.group(1) if match else None

VENDOR_ACCOUNTS["Burgmeier's Hauling"] = {
    'has_account': True,
    'format': 'NNNNNNN',
    'examples': ['1537213'],
    'extract': _extract_burgmeiers_hauling_account
}

def _extract_trash_control_account(text: str) -> Optional[str]:
    """Format: NNNNNN - Example: 003739"""
    match = re.search(r'(?:Customer)\s*#:?\s*(\d{5,7})', text, re.I)
    return match.group(1) if match else None

VENDOR_ACCOUNTS['Trash Control'] = {
    'has_account': True,
    'format': 'NNNNNN',
    'examples': ['003739'],
    'extract': _extract_trash_control_account
}

def _extract_haul_away_rubbish_account(text: str) -> Optional[str]:
    """Format: NNNNNN - Example: 509217"""
    match = re.search(r'(?:Account|Acct)\s*#:?\s*(\d{5,7})', text, re.I)
    return match.group(1) if match else None

VENDOR_ACCOUNTS['Haul Away Rubbish'] = {
    'has_account': True,
    'format': 'NNNNNN',
    'examples': ['509217'],
    'extract': _extract_haul_away_rubbish_account
}

def _extract_walters_sanitary_service_account(text: str) -> Optional[str]:
    """Format: NNNNNN - Example: 432626"""
    match = re.search(r'(?:Account|Acct)\s*#:?\s*(\d{5,7})', text, re.I)
    return match.group(1) if match else None

VENDOR_ACCOUNTS['Walters Sanitary Service'] = {
    'has_account': True,
    'format': 'NNNNNN',
    'examples': ['432626'],
    'extract': _extract_walters_sanitary_service_account
}

def _extract_filco_account(text: str) -> Optional[str]:
    """Format: NN-NNNNN - Example: 01-24650"""
    match = re.search(r'(?:Customer)\s*#:?\s*(\d{2}-\d{5})', text, re.I)
    return match.group(1) if match else None

VENDOR_ACCOUNTS['Filco'] = {
    'has_account': True,
    'format': 'NN-NNNNN',
    'examples': ['01-24650'],
    'extract': _extract_filco_account
}

def _extract_amber_disposal_account(text: str) -> Optional[str]:
    """Format: NNNNNN - Example: 453106"""
    match = re.search(r'(?:Account|Acct)\s*#:?\s*(\d{5,7})', text, re.I)
    return match.group(1) if match else None

VENDOR_ACCOUNTS['Amber Disposal'] = {
    'has_account': True,
    'format': 'NNNNNN',
    'examples': ['453106'],
    'extract': _extract_amber_disposal_account
}

def _extract_arts_garbage_account(text: str) -> Optional[str]:
    """Format: NNNNNN - Example: 271747"""
    match = re.search(r'(?:Account|Acct)\s*#:?\s*(\d{5,7})', text, re.I)
    return match.group(1) if match else None

VENDOR_ACCOUNTS["Art's Garbage"] = {
    'has_account': True,
    'format': 'NNNNNN',
    'examples': ['271747'],
    'extract': _extract_arts_garbage_account
}

def _extract_wyoming_waste_services_account(text: str) -> Optional[str]:
    """Format: NNNNNNN - Example: 1090841"""
    match = re.search(r'(?:Account|Acct)\s*#:?\s*(\d{6,8})', text, re.I)
    return match.group(1) if match else None

VENDOR_ACCOUNTS['Wyoming Waste Services'] = {
    'has_account': True,
    'format': 'NNNNNNN',
    'examples': ['1090841'],
    'extract': _extract_wyoming_waste_services_account
}

def _extract_trashco_account(text: str) -> Optional[str]:
    """Format: NN-NNNN - Example: 01-7469"""
    match = re.search(r'(?:Customer)\s*#:?\s*(\d{2}-\d{4})', text, re.I)
    return match.group(1) if match else None

VENDOR_ACCOUNTS['TRASHCO'] = {
    'has_account': True,
    'format': 'NN-NNNN',
    'examples': ['01-7469'],
    'extract': _extract_trashco_account
}

def _extract_ameriwaste_account(text: str) -> Optional[str]:
    """Format: NNNNN - Example: 42596"""
    match = re.search(r'(?:Account|Acct)\s*#:?\s*(\d{4,6})', text, re.I)
    return match.group(1) if match else None

VENDOR_ACCOUNTS['Ameriwaste'] = {
    'has_account': True,
    'format': 'NNNNN',
    'examples': ['42596'],
    'extract': _extract_ameriwaste_account
}

def _extract_absolute_waste_account(text: str) -> Optional[str]:
    """Format: NN-NNNNN - Example: 03-55573"""
    match = re.search(r'(?:Customer)\s*#:?\s*(\d{2}-\d{5})', text, re.I)
    return match.group(1) if match else None

VENDOR_ACCOUNTS['Absolute Waste'] = {
    'has_account': True,
    'format': 'NN-NNNNN',
    'examples': ['03-55573'],
    'extract': _extract_absolute_waste_account
}

def _extract_ssw_box_services_account(text: str) -> Optional[str]:
    """Format: NNNN - Example: 6194"""
    match = re.search(r'(?:Account|Acct)\s*#:?\s*(\d{3,5})', text, re.I)
    return match.group(1) if match else None

VENDOR_ACCOUNTS['SSW-Box Services'] = {
    'has_account': True,
    'format': 'NNNN',
    'examples': ['6194'],
    'extract': _extract_ssw_box_services_account
}

def _extract_hughes_trash_removal_account(text: str) -> Optional[str]:
    """Format: NNNNNN - Example: 611985"""
    match = re.search(r'(?:Account|Acct)\s*#:?\s*(\d{5,7})', text, re.I)
    return match.group(1) if match else None

VENDOR_ACCOUNTS['Hughes Trash Removal'] = {
    'has_account': True,
    'format': 'NNNNNN',
    'examples': ['611985'],
    'extract': _extract_hughes_trash_removal_account
}

def _extract_miamitown_auto_parts_account(text: str) -> Optional[str]:
    """Format: NNNNNNN - Example: 8526135"""
    match = re.search(r'(?:Account|Acct)\s*#:?\s*(\d{6,8})', text, re.I)
    return match.group(1) if match else None

VENDOR_ACCOUNTS['Miamitown Auto Parts'] = {
    'has_account': True,
    'format': 'NNNNNNN',
    'examples': ['8526135'],
    'extract': _extract_miamitown_auto_parts_account
}

def _extract_mt_diablo_resource_recovery_account(text: str) -> Optional[str]:
    """Format: NN-NNNNNNN - Example: 01-1036721"""
    match = re.search(r'(?:Customer)\s*#:?\s*(\d{2}-\d{7})', text, re.I)
    return match.group(1) if match else None

VENDOR_ACCOUNTS['Mt Diablo Resource Recovery'] = {
    'has_account': True,
    'format': 'NN-NNNNNNN',
    'examples': ['01-1036721'],
    'extract': _extract_mt_diablo_resource_recovery_account
}

def _extract_engebretson_sons_account(text: str) -> Optional[str]:
    """Format: NNNNNN - Example: 213744"""
    match = re.search(r'(?:Account|Acct)\s*#:?\s*(\d{5,7})', text, re.I)
    return match.group(1) if match else None

VENDOR_ACCOUNTS['Engebretson & Sons'] = {
    'has_account': True,
    'format': 'NNNNNN',
    'examples': ['213744'],
    'extract': _extract_engebretson_sons_account
}

def _extract_bloom_waste_account(text: str) -> Optional[str]:
    """Format: NNNNNN - Example: 572432"""
    match = re.search(r'(?:Account|Acct)\s*#:?\s*(\d{5,7})', text, re.I)
    return match.group(1) if match else None

VENDOR_ACCOUNTS['Bloom Waste'] = {
    'has_account': True,
    'format': 'NNNNNN',
    'examples': ['572432'],
    'extract': _extract_bloom_waste_account
}

def _extract_nauset_disposal_account(text: str) -> Optional[str]:
    """Format: NNNN-NNNNNNNN - Example: 6275-90427000"""
    match = re.search(r'(?:Account|Acct)\s*#:?\s*(\d{4}-\d{8})', text, re.I)
    return match.group(1) if match else None

VENDOR_ACCOUNTS['Nauset Disposal'] = {
    'has_account': True,
    'format': 'NNNN-NNNNNNNN',
    'examples': ['6275-90427000'],
    'extract': _extract_nauset_disposal_account
}

def _extract_redwood_waste_account(text: str) -> Optional[str]:
    """Format: NNNNNNN - Example: 6113030"""
    match = re.search(r'(?:Account|Acct)\s*#:?\s*(\d{6,8})', text, re.I)
    return match.group(1) if match else None

VENDOR_ACCOUNTS['Redwood Waste'] = {
    'has_account': True,
    'format': 'NNNNNNN',
    'examples': ['6113030'],
    'extract': _extract_redwood_waste_account
}

def _extract_waste_services_manchester_account(text: str) -> Optional[str]:
    """Format: NNNNNN - Example: 102087"""
    match = re.search(r'(?:Account|Acct)\s*#:?\s*(\d{5,7})', text, re.I)
    return match.group(1) if match else None

VENDOR_ACCOUNTS['Waste Services Manchester'] = {
    'has_account': True,
    'format': 'NNNNNN',
    'examples': ['102087'],
    'extract': _extract_waste_services_manchester_account
}

def _extract_keys_sanitary_account(text: str) -> Optional[str]:
    """Format: NNNNNN - Example: 351907"""
    match = re.search(r'(?:Account|Acct)\s*#:?\s*(\d{5,7})', text, re.I)
    return match.group(1) if match else None

VENDOR_ACCOUNTS['Keys Sanitary'] = {
    'has_account': True,
    'format': 'NNNNNN',
    'examples': ['351907'],
    'extract': _extract_keys_sanitary_account
}

def _extract_orlando_recycling_account(text: str) -> Optional[str]:
    """Format: NNNN - Example: 1604"""
    match = re.search(r'(?:Account|Acct)\s*#:?\s*(\d{3,5})', text, re.I)
    return match.group(1) if match else None

VENDOR_ACCOUNTS['Orlando Recycling'] = {
    'has_account': True,
    'format': 'NNNN',
    'examples': ['1604'],
    'extract': _extract_orlando_recycling_account
}

def _extract_madison_materials_account(text: str) -> Optional[str]:
    """Format: NNNNNN - Example: 113364"""
    match = re.search(r'(?:Account|Acct)\s*#:?\s*(\d{5,7})', text, re.I)
    return match.group(1) if match else None

VENDOR_ACCOUNTS['Madison Materials'] = {
    'has_account': True,
    'format': 'NNNNNN',
    'examples': ['113364'],
    'extract': _extract_madison_materials_account
}

def _extract_goode_companies_account(text: str) -> Optional[str]:
    """Format: NNNNNN - Example: 686747"""
    match = re.search(r'(?:Account|Acct)\s*#:?\s*(\d{5,7})', text, re.I)
    return match.group(1) if match else None

VENDOR_ACCOUNTS['Goode Companies'] = {
    'has_account': True,
    'format': 'NNNNNN',
    'examples': ['686747'],
    'extract': _extract_goode_companies_account
}

def _extract_fayette_waste_account(text: str) -> Optional[str]:
    """Format: NNNNNN - Example: 611835"""
    match = re.search(r'(?:Account|Acct)\s*#:?\s*(\d{5,7})', text, re.I)
    return match.group(1) if match else None

VENDOR_ACCOUNTS['Fayette Waste'] = {
    'has_account': True,
    'format': 'NNNNNN',
    'examples': ['611835'],
    'extract': _extract_fayette_waste_account
}

def _extract_california_waste_recovery_account(text: str) -> Optional[str]:
    """Format: NN-NNNNNNN-N - Example: 01-0048106-8"""
    match = re.search(r'(?:Customer)\s*#:?\s*(\d{2}-\d{7}-\d)', text, re.I)
    return match.group(1) if match else None

VENDOR_ACCOUNTS['California Waste Recovery'] = {
    'has_account': True,
    'format': 'NN-NNNNNNN-N',
    'examples': ['01-0048106-8'],
    'extract': _extract_california_waste_recovery_account
}

def _extract_roadrunner_rubbish_account(text: str) -> Optional[str]:
    """Format: NNNNNN - Example: 210231"""
    match = re.search(r'(?:Account|Acct)\s*#:?\s*(\d{5,7})', text, re.I)
    return match.group(1) if match else None

VENDOR_ACCOUNTS['Roadrunner Rubbish'] = {
    'has_account': True,
    'format': 'NNNNNN',
    'examples': ['210231'],
    'extract': _extract_roadrunner_rubbish_account
}

def _extract_texas_commercial_waste_account(text: str) -> Optional[str]:
    """Format: NN-NNNN - Example: 01-8178"""
    match = re.search(r'(?:Customer)\s*#:?\s*(\d{2}-\d{4})', text, re.I)
    return match.group(1) if match else None

VENDOR_ACCOUNTS['Texas Commercial Waste'] = {
    'has_account': True,
    'format': 'NN-NNNN',
    'examples': ['01-8178'],
    'extract': _extract_texas_commercial_waste_account
}

def _extract_jettison_environmental_account(text: str) -> Optional[str]:
    """Format: NNNNNN - Example: 204225"""
    match = re.search(r'(?:Account|Acct)\s*#:?\s*(\d{5,7})', text, re.I)
    return match.group(1) if match else None

VENDOR_ACCOUNTS['Jettison Environmental'] = {
    'has_account': True,
    'format': 'NNNNNN',
    'examples': ['204225'],
    'extract': _extract_jettison_environmental_account
}

def _extract_pacific_disposal_account(text: str) -> Optional[str]:
    """Format: NNNNNNN - Example: 1234794"""
    match = re.search(r'(?:Account|Acct)\s*#:?\s*(\d{6,8})', text, re.I)
    return match.group(1) if match else None

VENDOR_ACCOUNTS['Pacific Disposal'] = {
    'has_account': True,
    'format': 'NNNNNNN',
    'examples': ['1234794'],
    'extract': _extract_pacific_disposal_account
}

def _extract_denali_disposal_account(text: str) -> Optional[str]:
    """Format: NN-NNNNN - Example: 01-13029"""
    match = re.search(r'(?:Customer)\s*#:?\s*(\d{2}-\d{5})', text, re.I)
    return match.group(1) if match else None

VENDOR_ACCOUNTS['Denali Disposal'] = {
    'has_account': True,
    'format': 'NN-NNNNN',
    'examples': ['01-13029'],
    'extract': _extract_denali_disposal_account
}

def _extract_best_pick_disposal_account(text: str) -> Optional[str]:
    """Format: NNNNNNNN - Example: 14374502"""
    match = re.search(r'(?:Account|Acct)\s*#:?\s*(\d{7,9})', text, re.I)
    return match.group(1) if match else None

VENDOR_ACCOUNTS['Best Pick Disposal'] = {
    'has_account': True,
    'format': 'NNNNNNNN',
    'examples': ['14374502'],
    'extract': _extract_best_pick_disposal_account
}

def _extract_miles_city_sanitation_account(text: str) -> Optional[str]:
    """Format: NNNNNN - Example: 233614"""
    match = re.search(r'(?:Account|Acct)\s*#:?\s*(\d{5,7})', text, re.I)
    return match.group(1) if match else None

VENDOR_ACCOUNTS['Miles City Sanitation'] = {
    'has_account': True,
    'format': 'NNNNNN',
    'examples': ['233614'],
    'extract': _extract_miles_city_sanitation_account
}

def _extract_waste_advantage_account(text: str) -> Optional[str]:
    """Format: NN-NNNNN - Example: 01-37034"""
    match = re.search(r'(?:Customer)\s*#:?\s*(\d{2}-\d{5})', text, re.I)
    return match.group(1) if match else None

VENDOR_ACCOUNTS['Waste Advantage'] = {
    'has_account': True,
    'format': 'NN-NNNNN',
    'examples': ['01-37034'],
    'extract': _extract_waste_advantage_account
}

def _extract_econo_waste_account(text: str) -> Optional[str]:
    """Format: NNNNN - Example: 18199"""
    match = re.search(r'(?:Account|Acct)\s*#:?\s*(\d{4,6})', text, re.I)
    return match.group(1) if match else None

VENDOR_ACCOUNTS['Econo Waste'] = {
    'has_account': True,
    'format': 'NNNNN',
    'examples': ['18199'],
    'extract': _extract_econo_waste_account
}

def _extract_seaside_waste_account(text: str) -> Optional[str]:
    """Format: NN-NNNN - Example: 01-3351"""
    match = re.search(r'(?:Customer)\s*#:?\s*(\d{2}-\d{4})', text, re.I)
    return match.group(1) if match else None

VENDOR_ACCOUNTS['Seaside Waste'] = {
    'has_account': True,
    'format': 'NN-NNNN',
    'examples': ['01-3351'],
    'extract': _extract_seaside_waste_account
}

def _extract_timmons_waste_service_account(text: str) -> Optional[str]:
    """Format: NN-NNNNNN - Example: 01-162200"""
    match = re.search(r'(?:Customer)\s*#:?\s*(\d{2}-\d{6})', text, re.I)
    return match.group(1) if match else None

VENDOR_ACCOUNTS['Timmons Waste Service'] = {
    'has_account': True,
    'format': 'NN-NNNNNN',
    'examples': ['01-162200'],
    'extract': _extract_timmons_waste_service_account
}

def _extract_dedicated_dumpster_service_account(text: str) -> Optional[str]:
    """Format: NNNNN - Example: 14526"""
    match = re.search(r'(?:Account|Acct)\s*#:?\s*(\d{4,6})', text, re.I)
    return match.group(1) if match else None

VENDOR_ACCOUNTS['Dedicated Dumpster Service'] = {
    'has_account': True,
    'format': 'NNNNN',
    'examples': ['14526'],
    'extract': _extract_dedicated_dumpster_service_account
}

def _extract_hbs_denver_account(text: str) -> Optional[str]:
    """Format: NNNNNN - Example: 104461"""
    match = re.search(r'(?:Account|Acct)\s*#:?\s*(\d{5,7})', text, re.I)
    return match.group(1) if match else None

VENDOR_ACCOUNTS['HBS Denver'] = {
    'has_account': True,
    'format': 'NNNNNN',
    'examples': ['104461'],
    'extract': _extract_hbs_denver_account
}

def _extract_aws_account(text: str) -> Optional[str]:
    """Format: NN-NNNNNNN - Example: 10-6489149"""
    match = re.search(r'(?:Customer)\s*#:?\s*(\d{2}-\d{7})', text, re.I)
    return match.group(1) if match else None

VENDOR_ACCOUNTS['AWS'] = {
    'has_account': True,
    'format': 'NN-NNNNNNN',
    'examples': ['10-6489149'],
    'extract': _extract_aws_account
}

def _extract_town_country_disposal_account(text: str) -> Optional[str]:
    """Format: NNNNN - Example: 11001"""
    match = re.search(r'(?:Account|Acct)\s*#:?\s*(\d{4,6})', text, re.I)
    return match.group(1) if match else None

VENDOR_ACCOUNTS['Town & Country Disposal'] = {
    'has_account': True,
    'format': 'NNNNN',
    'examples': ['11001'],
    'extract': _extract_town_country_disposal_account
}

def _extract_modern_disposal_account(text: str) -> Optional[str]:
    """Format: NNNNNN - Example: 053262"""
    match = re.search(r'(?:Account|Acct)\s*#:?\s*(\d{5,7})', text, re.I)
    return match.group(1) if match else None

VENDOR_ACCOUNTS['Modern Disposal'] = {
    'has_account': True,
    'format': 'NNNNNN',
    'examples': ['053262'],
    'extract': _extract_modern_disposal_account
}

def _extract_bulldog_disposal_account(text: str) -> Optional[str]:
    """Format: NNNNNN - Example: 382074"""
    match = re.search(r'(?:Account|Acct)\s*#:?\s*(\d{5,7})', text, re.I)
    return match.group(1) if match else None

VENDOR_ACCOUNTS['Bulldog Disposal'] = {
    'has_account': True,
    'format': 'NNNNNN',
    'examples': ['382074'],
    'extract': _extract_bulldog_disposal_account
}

def _extract_city_of_grand_junction_account(text: str) -> Optional[str]:
    """Format: NNNNNN - Example: 116991"""
    match = re.search(r'(?:Account|Acct)\s*#:?\s*(\d{5,7})', text, re.I)
    return match.group(1) if match else None

VENDOR_ACCOUNTS['City of Grand Junction'] = {
    'has_account': True,
    'format': 'NNNNNN',
    'examples': ['116991'],
    'extract': _extract_city_of_grand_junction_account
}

def _extract_waste_services_inc_account(text: str) -> Optional[str]:
    """Format: NNNNNN - Example: 113044"""
    match = re.search(r'(?:Account|Acct)\s*#:?\s*(\d{5,7})', text, re.I)
    return match.group(1) if match else None

VENDOR_ACCOUNTS['Waste Services Inc'] = {
    'has_account': True,
    'format': 'NNNNNN',
    'examples': ['113044'],
    'extract': _extract_waste_services_inc_account
}

def _extract_rs_waste_account(text: str) -> Optional[str]:
    """Format: NN-NNNNN - Example: 02-46321"""
    match = re.search(r'(?:Customer)\s*#:?\s*(\d{2}-\d{5})', text, re.I)
    return match.group(1) if match else None

VENDOR_ACCOUNTS['R&S Waste'] = {
    'has_account': True,
    'format': 'NN-NNNNN',
    'examples': ['02-46321'],
    'extract': _extract_rs_waste_account
}

def _extract_whites_sanitation_account(text: str) -> Optional[str]:
    """Format: NNNNNN - Example: 421651"""
    match = re.search(r'(?:Account|Acct)\s*#:?\s*(\d{5,7})', text, re.I)
    return match.group(1) if match else None

VENDOR_ACCOUNTS['Whites Sanitation'] = {
    'has_account': True,
    'format': 'NNNNNN',
    'examples': ['421651'],
    'extract': _extract_whites_sanitation_account
}

def _extract_city_of_emporia_account(text: str) -> Optional[str]:
    """Format: NNNNN - Example: 28841"""
    match = re.search(r'(?:Account|Acct)\s*#:?\s*(\d{4,6})', text, re.I)
    return match.group(1) if match else None

VENDOR_ACCOUNTS['City of Emporia'] = {
    'has_account': True,
    'format': 'NNNNN',
    'examples': ['28841'],
    'extract': _extract_city_of_emporia_account
}

def _extract_city_of_foley_account(text: str) -> Optional[str]:
    """Format: NN-NNNN - Example: 01-1735"""
    match = re.search(r'(?:Customer)\s*#:?\s*(\d{2}-\d{4})', text, re.I)
    return match.group(1) if match else None

VENDOR_ACCOUNTS['City of Foley'] = {
    'has_account': True,
    'format': 'NN-NNNN',
    'examples': ['01-1735'],
    'extract': _extract_city_of_foley_account
}

def _extract_eastern_waste_account(text: str) -> Optional[str]:
    """Format: NN-NNNN - Example: 03-5144"""
    match = re.search(r'(?:Customer)\s*#:?\s*(\d{2}-\d{4})', text, re.I)
    return match.group(1) if match else None

VENDOR_ACCOUNTS['Eastern Waste'] = {
    'has_account': True,
    'format': 'NN-NNNN',
    'examples': ['03-5144'],
    'extract': _extract_eastern_waste_account
}

def _extract_shulars_trash_service_account(text: str) -> Optional[str]:
    """Format: NNNN - Example: 4501"""
    match = re.search(r'(?:Account|Acct)\s*#:?\s*(\d{3,5})', text, re.I)
    return match.group(1) if match else None

VENDOR_ACCOUNTS["Shular's Trash Service"] = {
    'has_account': True,
    'format': 'NNNN',
    'examples': ['4501'],
    'extract': _extract_shulars_trash_service_account
}

def _extract_cheyenne_board_public_utilities_account(text: str) -> Optional[str]:
    """Format: NNNNNN - Example: 668376"""
    match = re.search(r'(?:Account|Acct)\s*#:?\s*(\d{5,7})', text, re.I)
    return match.group(1) if match else None

VENDOR_ACCOUNTS['Cheyenne Board of Public Utilities'] = {
    'has_account': True,
    'format': 'NNNNNN',
    'examples': ['668376'],
    'extract': _extract_cheyenne_board_public_utilities_account
}

def _extract_waste_partners_account(text: str) -> Optional[str]:
    """Format: NNNNNN - Example: 498813"""
    match = re.search(r'(?:Account|Acct)\s*#:?\s*(\d{5,7})', text, re.I)
    return match.group(1) if match else None

VENDOR_ACCOUNTS['Waste Partners'] = {
    'has_account': True,
    'format': 'NNNNNN',
    'examples': ['498813'],
    'extract': _extract_waste_partners_account
}

def _extract_garland_county_landfill_account(text: str) -> Optional[str]:
    """Format: NN-NNN - Example: 01-144"""
    match = re.search(r'(?:Customer)\s*#:?\s*(\d{2}-\d{3})', text, re.I)
    return match.group(1) if match else None

VENDOR_ACCOUNTS['Garland County Landfill'] = {
    'has_account': True,
    'format': 'NN-NNN',
    'examples': ['01-144'],
    'extract': _extract_garland_county_landfill_account
}

def _extract_city_lakes_disposal_account(text: str) -> Optional[str]:
    """Format: NNNNNN - Example: 453932"""
    match = re.search(r'(?:Account|Acct)\s*#:?\s*(\d{5,7})', text, re.I)
    return match.group(1) if match else None

VENDOR_ACCOUNTS['City & Lakes Disposal'] = {
    'has_account': True,
    'format': 'NNNNNN',
    'examples': ['453932'],
    'extract': _extract_city_lakes_disposal_account
}

def _extract_evergreen_paper_recycling_account(text: str) -> Optional[str]:
    """Format: NNNNNNNNN - Example: 830047007"""
    match = re.search(r'(?:Account|Acct)\s*#:?\s*(\d{8,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_ACCOUNTS['Evergreen Paper Recycling'] = {
    'has_account': True,
    'format': 'NNNNNNNNN',
    'examples': ['830047007'],
    'extract': _extract_evergreen_paper_recycling_account
}

def _extract_american_eagle_waste_account(text: str) -> Optional[str]:
    """Format: NNNNNN - Example: 732305"""
    match = re.search(r'(?:Account|Acct)\s*#:?\s*(\d{5,7})', text, re.I)
    return match.group(1) if match else None

VENDOR_ACCOUNTS['American Eagle Waste'] = {
    'has_account': True,
    'format': 'NNNNNN',
    'examples': ['732305'],
    'extract': _extract_american_eagle_waste_account
}

def _extract_bright_disposal_services_account(text: str) -> Optional[str]:
    """Format: NNNN - Example: 5214"""
    match = re.search(r'(?:Account|Acct)\s*#:?\s*(\d{3,5})', text, re.I)
    return match.group(1) if match else None

VENDOR_ACCOUNTS['Bright Disposal Services'] = {
    'has_account': True,
    'format': 'NNNN',
    'examples': ['5214'],
    'extract': _extract_bright_disposal_services_account
}

def _extract_empire_disposal_account(text: str) -> Optional[str]:
    """Format: NNNN-NNNNNNN - Example: 2120-1152029"""
    match = re.search(r'(?:Customer)\s*#:?\s*(\d{4}-\d{7})', text, re.I)
    return match.group(1) if match else None

VENDOR_ACCOUNTS['Empire Disposal'] = {
    'has_account': True,
    'format': 'NNNN-NNNNNNN',
    'examples': ['2120-1152029'],
    'extract': _extract_empire_disposal_account
}

def _extract_waterman_recy_disposal_account(text: str) -> Optional[str]:
    """Format: NNNNN - Example: 18955"""
    match = re.search(r'(?:Account|Acct)\s*#:?\s*(\d{4,6})', text, re.I)
    return match.group(1) if match else None

VENDOR_ACCOUNTS['Waterman Recy & Disposal'] = {
    'has_account': True,
    'format': 'NNNNN',
    'examples': ['18955'],
    'extract': _extract_waterman_recy_disposal_account
}

def _extract_new_prague_sanitary_account(text: str) -> Optional[str]:
    """Format: NN-NNNNN - Example: 01-16548"""
    match = re.search(r'(?:Customer)\s*#:?\s*(\d{2}-\d{5})', text, re.I)
    return match.group(1) if match else None

VENDOR_ACCOUNTS['New Prague Sanitary'] = {
    'has_account': True,
    'format': 'NN-NNNNN',
    'examples': ['01-16548'],
    'extract': _extract_new_prague_sanitary_account
}

def _extract_chisago_lakes_sanitation_account(text: str) -> Optional[str]:
    """Format: NNNNNN - Example: 440622"""
    match = re.search(r'(?:Account|Acct)\s*#:?\s*(\d{5,7})', text, re.I)
    return match.group(1) if match else None

VENDOR_ACCOUNTS['Chisago Lakes Sanitation'] = {
    'has_account': True,
    'format': 'NNNNNN',
    'examples': ['440622'],
    'extract': _extract_chisago_lakes_sanitation_account
}

def _extract_jim_dedmans_sanitation_account(text: str) -> Optional[str]:
    """Format: NNNNN - Example: 22524"""
    match = re.search(r'(?:Account|Acct)\s*#:?\s*(\d{4,6})', text, re.I)
    return match.group(1) if match else None

VENDOR_ACCOUNTS["Jim Dedman's Sanitation"] = {
    'has_account': True,
    'format': 'NNNNN',
    'examples': ['22524'],
    'extract': _extract_jim_dedmans_sanitation_account
}

def _extract_waste_control_account(text: str) -> Optional[str]:
    """Format: NNNNNN - Example: 038150"""
    match = re.search(r'(?:Account|Acct)\s*#:?\s*(\d{5,7})', text, re.I)
    return match.group(1) if match else None

VENDOR_ACCOUNTS['Waste Control'] = {
    'has_account': True,
    'format': 'NNNNNN',
    'examples': ['038150'],
    'extract': _extract_waste_control_account
}

def _extract_absolute_services_account(text: str) -> Optional[str]:
    """Format: NN-NNN - Example: 10-460"""
    match = re.search(r'(?:Customer)\s*#:?\s*(\d{2}-\d{3})', text, re.I)
    return match.group(1) if match else None

VENDOR_ACCOUNTS['Absolute Services'] = {
    'has_account': True,
    'format': 'NN-NNN',
    'examples': ['10-460'],
    'extract': _extract_absolute_services_account
}

def _extract_mr_e_account(text: str) -> Optional[str]:
    """Format: NNNN - Example: 2754"""
    match = re.search(r'(?:Account|Acct)\s*#:?\s*(\d{3,5})', text, re.I)
    return match.group(1) if match else None

VENDOR_ACCOUNTS['MR & E'] = {
    'has_account': True,
    'format': 'NNNN',
    'examples': ['2754'],
    'extract': _extract_mr_e_account
}

def _extract_city_of_lakeland_fl_account(text: str) -> Optional[str]:
    """Format: NNNNNNN - Example: 3692208"""
    match = re.search(r'(?:Account|Acct)\s*#:?\s*(\d{6,8})', text, re.I)
    return match.group(1) if match else None

VENDOR_ACCOUNTS['City of Lakeland FL'] = {
    'has_account': True,
    'format': 'NNNNNNN',
    'examples': ['3692208'],
    'extract': _extract_city_of_lakeland_fl_account
}

def _extract_town_of_gardnerville_account(text: str) -> Optional[str]:
    """Format: NNNNNN - Example: 306214"""
    match = re.search(r'(?:Account|Acct)\s*#:?\s*(\d{5,7})', text, re.I)
    return match.group(1) if match else None

VENDOR_ACCOUNTS['Town of Gardnerville'] = {
    'has_account': True,
    'format': 'NNNNNN',
    'examples': ['306214'],
    'extract': _extract_town_of_gardnerville_account
}

def _extract_thomas_trash_account(text: str) -> Optional[str]:
    """Format: NNNNNN - Example: 283722"""
    match = re.search(r'(?:Account|Acct)\s*#:?\s*(\d{5,7})', text, re.I)
    return match.group(1) if match else None

VENDOR_ACCOUNTS['Thomas Trash'] = {
    'has_account': True,
    'format': 'NNNNNN',
    'examples': ['283722'],
    'extract': _extract_thomas_trash_account
}

def _extract_humboldt_county_landfill_account(text: str) -> Optional[str]:
    """Format: NNNN - Example: 0469"""
    match = re.search(r'(?:Account|Acct)\s*#:?\s*(\d{3,5})', text, re.I)
    return match.group(1) if match else None

VENDOR_ACCOUNTS['Humboldt County Landfill'] = {
    'has_account': True,
    'format': 'NNNN',
    'examples': ['0469'],
    'extract': _extract_humboldt_county_landfill_account
}

def _extract_westbury_paper_stock_account(text: str) -> Optional[str]:
    """Format: NNNNNN - Example: 453073"""
    match = re.search(r'(?:Account|Acct)\s*#:?\s*(\d{5,7})', text, re.I)
    return match.group(1) if match else None

VENDOR_ACCOUNTS['Westbury Paper Stock'] = {
    'has_account': True,
    'format': 'NNNNNN',
    'examples': ['453073'],
    'extract': _extract_westbury_paper_stock_account
}

def _extract_mountain_high_disposal_account(text: str) -> Optional[str]:
    """Format: NN-NNNNN - Example: 04-48659"""
    match = re.search(r'(?:Customer)\s*#:?\s*(\d{2}-\d{5})', text, re.I)
    return match.group(1) if match else None

VENDOR_ACCOUNTS['Mountain High Disposal'] = {
    'has_account': True,
    'format': 'NN-NNNNN',
    'examples': ['04-48659'],
    'extract': _extract_mountain_high_disposal_account
}

def _extract_westside_waste_management_account(text: str) -> Optional[str]:
    """Format: NN-NNNNN - Example: 01-31720"""
    match = re.search(r'(?:Customer)\s*#:?\s*(\d{2}-\d{5})', text, re.I)
    return match.group(1) if match else None

VENDOR_ACCOUNTS['Westside Waste Management'] = {
    'has_account': True,
    'format': 'NN-NNNNN',
    'examples': ['01-31720'],
    'extract': _extract_westside_waste_management_account
}

def _extract_city_of_winfield_account(text: str) -> Optional[str]:
    """Format: NNNNNN - Example: 105323"""
    match = re.search(r'(?:Account|Acct)\s*#:?\s*(\d{5,7})', text, re.I)
    return match.group(1) if match else None

VENDOR_ACCOUNTS['City of Winfield'] = {
    'has_account': True,
    'format': 'NNNNNN',
    'examples': ['105323'],
    'extract': _extract_city_of_winfield_account
}

def _extract_gilton_solid_waste_account(text: str) -> Optional[str]:
    """Format: NNNNNNNNN-NN - Example: 000110265-04"""
    match = re.search(r'(?:Account|Acct)\s*#:?\s*(\d{9}-\d{2})', text, re.I)
    return match.group(1) if match else None

VENDOR_ACCOUNTS['Gilton Solid Waste'] = {
    'has_account': True,
    'format': 'NNNNNNNNN-NN',
    'examples': ['000110265-04'],
    'extract': _extract_gilton_solid_waste_account
}

def _extract_torrez_sanitation_account(text: str) -> Optional[str]:
    """Format: NNNN - Example: 8708"""
    match = re.search(r'(?:Account|Acct)\s*#:?\s*(\d{3,5})', text, re.I)
    return match.group(1) if match else None

VENDOR_ACCOUNTS['Torrez Sanitation'] = {
    'has_account': True,
    'format': 'NNNN',
    'examples': ['8708'],
    'extract': _extract_torrez_sanitation_account
}

def _extract_sound_disposal_inc_account(text: str) -> Optional[str]:
    """Format: NNNNNN - Example: 202806"""
    match = re.search(r'(?:Account|Acct)\s*#:?\s*(\d{5,7})', text, re.I)
    return match.group(1) if match else None

VENDOR_ACCOUNTS['Sound Disposal Inc'] = {
    'has_account': True,
    'format': 'NNNNNN',
    'examples': ['202806'],
    'extract': _extract_sound_disposal_inc_account
}

def _extract_buckingham_companies_account(text: str) -> Optional[str]:
    """Format: NN-NNNNN - Example: 02-26621"""
    match = re.search(r'(?:Customer)\s*#:?\s*(\d{2}-\d{5})', text, re.I)
    return match.group(1) if match else None

VENDOR_ACCOUNTS['Buckingham Companies'] = {
    'has_account': True,
    'format': 'NN-NNNNN',
    'examples': ['02-26621'],
    'extract': _extract_buckingham_companies_account
}

def _extract_key_disposal_recycling_account(text: str) -> Optional[str]:
    """Format: NNNNNN - Example: 648667"""
    match = re.search(r'(?:Account|Acct)\s*#:?\s*(\d{5,7})', text, re.I)
    return match.group(1) if match else None

VENDOR_ACCOUNTS['Key Disposal & Recycling'] = {
    'has_account': True,
    'format': 'NNNNNN',
    'examples': ['648667'],
    'extract': _extract_key_disposal_recycling_account
}

def _extract_tbs_waste_account(text: str) -> Optional[str]:
    """Format: NNNNNN - Example: 541752"""
    match = re.search(r'(?:Account|Acct)\s*#:?\s*(\d{5,7})', text, re.I)
    return match.group(1) if match else None

VENDOR_ACCOUNTS['TBS Waste'] = {
    'has_account': True,
    'format': 'NNNNNN',
    'examples': ['541752'],
    'extract': _extract_tbs_waste_account
}

def _extract_city_of_cartersville_account(text: str) -> Optional[str]:
    """Format: NNNNNNN-NNNNNN - Example: 5011166-203681"""
    match = re.search(r'(?:Account|Acct)\s*#:?\s*(\d{7}-\d{6})', text, re.I)
    return match.group(1) if match else None

VENDOR_ACCOUNTS['City of Cartersville'] = {
    'has_account': True,
    'format': 'NNNNNNN-NNNNNN',
    'examples': ['5011166-203681'],
    'extract': _extract_city_of_cartersville_account
}

def _extract_fritz_enterprises_account(text: str) -> Optional[str]:
    """Format: NNNNNN - Example: 239021"""
    match = re.search(r'(?:Account|Acct)\s*#:?\s*(\d{5,7})', text, re.I)
    return match.group(1) if match else None

VENDOR_ACCOUNTS['Fritz Enterprises'] = {
    'has_account': True,
    'format': 'NNNNNN',
    'examples': ['239021'],
    'extract': _extract_fritz_enterprises_account
}

def _extract_sanitation_services_account(text: str) -> Optional[str]:
    """Format: NNNNNN - Example: 002657"""
    match = re.search(r'(?:Account|Acct)\s*#:?\s*(\d{5,7})', text, re.I)
    return match.group(1) if match else None

VENDOR_ACCOUNTS['Sanitation Services'] = {
    'has_account': True,
    'format': 'NNNNNN',
    'examples': ['002657'],
    'extract': _extract_sanitation_services_account
}

def _extract_city_of_mount_vernon_wa_account(text: str) -> Optional[str]:
    """Format: NN-NNNNNN - Example: 83-001720"""
    match = re.search(r'(?:Customer)\s*#:?\s*(\d{2}-\d{6})', text, re.I)
    return match.group(1) if match else None

VENDOR_ACCOUNTS['City of Mount Vernon WA'] = {
    'has_account': True,
    'format': 'NN-NNNNNN',
    'examples': ['83-001720'],
    'extract': _extract_city_of_mount_vernon_wa_account
}

def _extract_less_sanitation_account(text: str) -> Optional[str]:
    """Format: NNNNNN - Example: 671803"""
    match = re.search(r'(?:Account|Acct)\s*#:?\s*(\d{5,7})', text, re.I)
    return match.group(1) if match else None

VENDOR_ACCOUNTS["Les's Sanitation"] = {
    'has_account': True,
    'format': 'NNNNNN',
    'examples': ['671803'],
    'extract': _extract_less_sanitation_account
}

def _extract_aztec_waste_account(text: str) -> Optional[str]:
    """Format: NNNNNN - Example: 227153"""
    match = re.search(r'(?:Account|Acct)\s*#:?\s*(\d{5,7})', text, re.I)
    return match.group(1) if match else None

VENDOR_ACCOUNTS['Aztec Waste'] = {
    'has_account': True,
    'format': 'NNNNNN',
    'examples': ['227153'],
    'extract': _extract_aztec_waste_account
}

def _extract_waste_disposal_az_account(text: str) -> Optional[str]:
    """Format: NNNNNNN - Example: 1797473"""
    match = re.search(r'(?:Account|Acct)\s*#:?\s*(\d{6,8})', text, re.I)
    return match.group(1) if match else None

VENDOR_ACCOUNTS['Waste Disposal AZ'] = {
    'has_account': True,
    'format': 'NNNNNNN',
    'examples': ['1797473'],
    'extract': _extract_waste_disposal_az_account
}

def _extract_davids_trash_service_account(text: str) -> Optional[str]:
    """Format: NNNNN - Example: 17284"""
    match = re.search(r'(?:Account|Acct)\s*#:?\s*(\d{4,6})', text, re.I)
    return match.group(1) if match else None

VENDOR_ACCOUNTS["David's Trash Service"] = {
    'has_account': True,
    'format': 'NNNNN',
    'examples': ['17284'],
    'extract': _extract_davids_trash_service_account
}

def _extract_fisk_waste_removal_account(text: str) -> Optional[str]:
    """Format: NNNNNN - Example: 312081"""
    match = re.search(r'(?:Account|Acct)\s*#:?\s*(\d{5,7})', text, re.I)
    return match.group(1) if match else None

VENDOR_ACCOUNTS['Fisk Waste Removal'] = {
    'has_account': True,
    'format': 'NNNNNN',
    'examples': ['312081'],
    'extract': _extract_fisk_waste_removal_account
}

def _extract_mcallen_public_utility_account(text: str) -> Optional[str]:
    """Format: NNNNNNNN - Example: 00066905"""
    match = re.search(r'(?:Account|Acct)\s*#:?\s*(\d{7,9})', text, re.I)
    return match.group(1) if match else None

VENDOR_ACCOUNTS['McAllen Public Utility'] = {
    'has_account': True,
    'format': 'NNNNNNNN',
    'examples': ['00066905'],
    'extract': _extract_mcallen_public_utility_account
}

def _extract_g_h_garbage_account(text: str) -> Optional[str]:
    """Format: NNNNNN - Example: 405973"""
    match = re.search(r'(?:Account|Acct)\s*#:?\s*(\d{5,7})', text, re.I)
    return match.group(1) if match else None

VENDOR_ACCOUNTS['G & H Garbage'] = {
    'has_account': True,
    'format': 'NNNNNN',
    'examples': ['405973'],
    'extract': _extract_g_h_garbage_account
}

def _extract_ds_waste_account(text: str) -> Optional[str]:
    """Format: NNNNNN - Example: 316390"""
    match = re.search(r'(?:Account|Acct)\s*#:?\s*(\d{5,7})', text, re.I)
    return match.group(1) if match else None

VENDOR_ACCOUNTS['D&S Waste'] = {
    'has_account': True,
    'format': 'NNNNNN',
    'examples': ['316390'],
    'extract': _extract_ds_waste_account
}

def _extract_city_of_casper_account(text: str) -> Optional[str]:
    """Format: NNNNNN - Example: 202284"""
    match = re.search(r'(?:Account|Acct)\s*#:?\s*(\d{5,7})', text, re.I)
    return match.group(1) if match else None

VENDOR_ACCOUNTS['City of Casper'] = {
    'has_account': True,
    'format': 'NNNNNN',
    'examples': ['202284'],
    'extract': _extract_city_of_casper_account
}

def _extract_green_river_waste_account(text: str) -> Optional[str]:
    """Format: NNNNNN - Example: 434434"""
    match = re.search(r'(?:Account|Acct)\s*#:?\s*(\d{5,7})', text, re.I)
    return match.group(1) if match else None

VENDOR_ACCOUNTS['Green River Waste'] = {
    'has_account': True,
    'format': 'NNNNNN',
    'examples': ['434434'],
    'extract': _extract_green_river_waste_account
}

def _extract_irow_account(text: str) -> Optional[str]:
    """Format: NNNNNN - Example: 002371"""
    match = re.search(r'(?:Account|Acct)\s*#:?\s*(\d{5,7})', text, re.I)
    return match.group(1) if match else None

VENDOR_ACCOUNTS['IROW'] = {
    'has_account': True,
    'format': 'NNNNNN',
    'examples': ['002371'],
    'extract': _extract_irow_account
}

def _extract_busy_bee_disposal_account(text: str) -> Optional[str]:
    """Format: NNNN - Example: 3886"""
    match = re.search(r'(?:Account|Acct)\s*#:?\s*(\d{3,5})', text, re.I)
    return match.group(1) if match else None

VENDOR_ACCOUNTS['Busy Bee Disposal'] = {
    'has_account': True,
    'format': 'NNNN',
    'examples': ['3886'],
    'extract': _extract_busy_bee_disposal_account
}

def _extract_opdenaker_trash_account(text: str) -> Optional[str]:
    """Format: NNNNNNNN - Example: 14242300"""
    match = re.search(r'(?:Account|Acct)\s*#:?\s*(\d{7,9})', text, re.I)
    return match.group(1) if match else None

VENDOR_ACCOUNTS['Opdenaker Trash'] = {
    'has_account': True,
    'format': 'NNNNNNNN',
    'examples': ['14242300'],
    'extract': _extract_opdenaker_trash_account
}

def _extract_murray_sanitation_account(text: str) -> Optional[str]:
    """Format: NN-NNN - Example: 03-496"""
    match = re.search(r'(?:Customer)\s*#:?\s*(\d{2}-\d{3})', text, re.I)
    return match.group(1) if match else None

VENDOR_ACCOUNTS['Murray Sanitation'] = {
    'has_account': True,
    'format': 'NN-NNN',
    'examples': ['03-496'],
    'extract': _extract_murray_sanitation_account
}

def _extract_all_states_rentals_account(text: str) -> Optional[str]:
    """Format: NN-NNNNNNN - Example: 01-0100117"""
    match = re.search(r'(?:Customer)\s*#:?\s*(\d{2}-\d{7})', text, re.I)
    return match.group(1) if match else None

VENDOR_ACCOUNTS['All States Rentals'] = {
    'has_account': True,
    'format': 'NN-NNNNNNN',
    'examples': ['01-0100117'],
    'extract': _extract_all_states_rentals_account
}

def _extract_malcom_enterprises_account(text: str) -> Optional[str]:
    """Format: NNNN - Example: 6184"""
    match = re.search(r'(?:Account|Acct)\s*#:?\s*(\d{3,5})', text, re.I)
    return match.group(1) if match else None

VENDOR_ACCOUNTS['Malcom Enterprises'] = {
    'has_account': True,
    'format': 'NNNN',
    'examples': ['6184'],
    'extract': _extract_malcom_enterprises_account
}

def _extract_town_of_babylon_account(text: str) -> Optional[str]:
    """Format: NNNNNNNN - Example: 01000231"""
    match = re.search(r'(?:Account|Acct)\s*#:?\s*(\d{7,9})', text, re.I)
    return match.group(1) if match else None

VENDOR_ACCOUNTS['Town of Babylon'] = {
    'has_account': True,
    'format': 'NNNNNNNN',
    'examples': ['01000231'],
    'extract': _extract_town_of_babylon_account
}

def _extract_all_states_services_account(text: str) -> Optional[str]:
    """Format: NN-NNNNNNN - Example: 09-0228745"""
    match = re.search(r'(?:Customer)\s*#:?\s*(\d{2}-\d{7})', text, re.I)
    return match.group(1) if match else None

VENDOR_ACCOUNTS['All States Services'] = {
    'has_account': True,
    'format': 'NN-NNNNNNN',
    'examples': ['09-0228745'],
    'extract': _extract_all_states_services_account
}

def _extract_city_of_baxley_account(text: str) -> Optional[str]:
    """Format: NNNNNN - Example: 006861"""
    match = re.search(r'(?:Account|Acct)\s*#:?\s*(\d{5,7})', text, re.I)
    return match.group(1) if match else None

VENDOR_ACCOUNTS['City of Baxley'] = {
    'has_account': True,
    'format': 'NNNNNN',
    'examples': ['006861'],
    'extract': _extract_city_of_baxley_account
}

def _extract_cook_sanitation_account(text: str) -> Optional[str]:
    """Format: NNNN - Example: 3778"""
    match = re.search(r'(?:Account|Acct)\s*#:?\s*(\d{3,5})', text, re.I)
    return match.group(1) if match else None

VENDOR_ACCOUNTS['Cook Sanitation'] = {
    'has_account': True,
    'format': 'NNNN',
    'examples': ['3778'],
    'extract': _extract_cook_sanitation_account
}

def _extract_harley_hollan_account(text: str) -> Optional[str]:
    """Format: NN-NNNNN - Example: 01-58733"""
    match = re.search(r'(?:Customer)\s*#:?\s*(\d{2}-\d{5})', text, re.I)
    return match.group(1) if match else None

VENDOR_ACCOUNTS['Harley Hollan'] = {
    'has_account': True,
    'format': 'NN-NNNNN',
    'examples': ['01-58733'],
    'extract': _extract_harley_hollan_account
}

def _extract_jj_sanitation_account(text: str) -> Optional[str]:
    """Format: NNNNNN - Example: 229735"""
    match = re.search(r'(?:Account|Acct)\s*#:?\s*(\d{5,7})', text, re.I)
    return match.group(1) if match else None

VENDOR_ACCOUNTS['J&J Sanitation'] = {
    'has_account': True,
    'format': 'NNNNNN',
    'examples': ['229735'],
    'extract': _extract_jj_sanitation_account
}

def _extract_southland_environmental_account(text: str) -> Optional[str]:
    """Format: NNNNNN - Example: 133400"""
    match = re.search(r'(?:Account|Acct)\s*#:?\s*(\d{5,7})', text, re.I)
    return match.group(1) if match else None

VENDOR_ACCOUNTS['Southland Environmental'] = {
    'has_account': True,
    'format': 'NNNNNN',
    'examples': ['133400'],
    'extract': _extract_southland_environmental_account
}

def _extract_ts_trash_service_account(text: str) -> Optional[str]:
    """Format: NNNN - Example: 5482"""
    match = re.search(r'(?:Account|Acct)\s*#:?\s*(\d{3,5})', text, re.I)
    return match.group(1) if match else None

VENDOR_ACCOUNTS['T & S Trash Service'] = {
    'has_account': True,
    'format': 'NNNN',
    'examples': ['5482'],
    'extract': _extract_ts_trash_service_account
}


# ============================================================
# V8 AUTO-GENERATED EXTRACTORS - Batch 2 (41 more vendors)
# ============================================================

def _extract_olympic_compactor_rentals_account(text: str) -> Optional[str]:
    """Format: NN-NNNNNNN - Example: 01-0080030"""
    match = re.search(r'CUSTOMER\s*NO\.?:?\s*(\d{2}-\d{7})', text, re.I)
    return match.group(1) if match else None

VENDOR_ACCOUNTS['Olympic Compactor Rentals'] = {
    'has_account': True,
    'format': 'NN-NNNNNNN',
    'examples': ['01-0080030'],
    'extract': _extract_olympic_compactor_rentals_account
}

def _extract_cleeton_sanitation_account(text: str) -> Optional[str]:
    """Format: NNNNNN - Example: 439987"""
    match = re.search(r'Account\s*No:?\s*(\d{5,7})', text, re.I)
    return match.group(1) if match else None

VENDOR_ACCOUNTS['Cleeton Sanitation'] = {
    'has_account': True,
    'format': 'NNNNNN',
    'examples': ['439987'],
    'extract': _extract_cleeton_sanitation_account
}

def _extract_city_of_fargo_account(text: str) -> Optional[str]:
    """Format: NNNNN - Example: 20334"""
    match = re.search(r'Customer\s*No:?\s*(\d{4,6})', text, re.I)
    return match.group(1) if match else None

VENDOR_ACCOUNTS['City of Fargo'] = {
    'has_account': True,
    'format': 'NNNNN',
    'examples': ['20334'],
    'extract': _extract_city_of_fargo_account
}

def _extract_advance_disposal_account(text: str) -> Optional[str]:
    """Format: NNNNNN - Example: 076006"""
    match = re.search(r'Account\s*Number:?\s*(\d{5,7})', text, re.I)
    return match.group(1) if match else None

VENDOR_ACCOUNTS['Advance Disposal'] = {
    'has_account': True,
    'format': 'NNNNNN',
    'examples': ['076006'],
    'extract': _extract_advance_disposal_account
}

def _extract_midwest_sanitation_account(text: str) -> Optional[str]:
    """Format: NNNNNNN - Example: 3549500"""
    match = re.search(r'ACCT\.?\s*NO\.?:?\s*(\d{6,8})', text, re.I)
    return match.group(1) if match else None

VENDOR_ACCOUNTS['Midwest Sanitation'] = {
    'has_account': True,
    'format': 'NNNNNNN',
    'examples': ['3549500'],
    'extract': _extract_midwest_sanitation_account
}

def _extract_k_k_sanitation_account(text: str) -> Optional[str]:
    """Format: NNNNNN - Example: 120333"""
    match = re.search(r'Account\s*Number:?\s*(\d{5,7})', text, re.I)
    return match.group(1) if match else None

VENDOR_ACCOUNTS['K & K Sanitation'] = {
    'has_account': True,
    'format': 'NNNNNN',
    'examples': ['120333'],
    'extract': _extract_k_k_sanitation_account
}

def _extract_glendale_arizona_utilities_account(text: str) -> Optional[str]:
    """Format: NNNNNNNN - Example: 00327535"""
    match = re.search(r'Account\s*Number:?\s*(\d{7,9})', text, re.I)
    return match.group(1) if match else None

VENDOR_ACCOUNTS['Glendale Arizona Utilities'] = {
    'has_account': True,
    'format': 'NNNNNNNN',
    'examples': ['00327535'],
    'extract': _extract_glendale_arizona_utilities_account
}

def _extract_city_of_mesquite_account(text: str) -> Optional[str]:
    """Format: NNNNNN - Example: 670000"""
    match = re.search(r'ACCT\.?\s*NO\.?:?\s*(\d{5,7})', text, re.I)
    return match.group(1) if match else None

VENDOR_ACCOUNTS['City of Mesquite'] = {
    'has_account': True,
    'format': 'NNNNNN',
    'examples': ['670000'],
    'extract': _extract_city_of_mesquite_account
}

def _extract_city_sanitary_service_account(text: str) -> Optional[str]:
    """Format: NNNNN - Example: 11966"""
    match = re.search(r'Account\s*Number:?\s*(\d{4,6})', text, re.I)
    return match.group(1) if match else None

VENDOR_ACCOUNTS['City Sanitary Service'] = {
    'has_account': True,
    'format': 'NNNNN',
    'examples': ['11966'],
    'extract': _extract_city_sanitary_service_account
}

def _extract_talon_sanitation_account(text: str) -> Optional[str]:
    """Format: NNNNNN - Example: 130322"""
    match = re.search(r'Account\s*Number:?\s*(\d{5,7})', text, re.I)
    return match.group(1) if match else None

VENDOR_ACCOUNTS['Talon Sanitation'] = {
    'has_account': True,
    'format': 'NNNNNN',
    'examples': ['130322'],
    'extract': _extract_talon_sanitation_account
}

def _extract_arrowhead_waste_account(text: str) -> Optional[str]:
    """Format: NNNNNN - Example: 107236"""
    match = re.search(r'Account\s*Number:?\s*(\d{5,7})', text, re.I)
    return match.group(1) if match else None

VENDOR_ACCOUNTS['Arrowhead Waste'] = {
    'has_account': True,
    'format': 'NNNNNN',
    'examples': ['107236'],
    'extract': _extract_arrowhead_waste_account
}

def _extract_pm_reis_trucking_account(text: str) -> Optional[str]:
    """Format: NNNNNN - Example: 209041"""
    match = re.search(r'Account\s*Number:?\s*(\d{5,7})', text, re.I)
    return match.group(1) if match else None

VENDOR_ACCOUNTS['P&M Reis Trucking'] = {
    'has_account': True,
    'format': 'NNNNNN',
    'examples': ['209041'],
    'extract': _extract_pm_reis_trucking_account
}

def _extract_olathe_kansas_account(text: str) -> Optional[str]:
    """Format: NNNNNNNN - Example: 99006605"""
    match = re.search(r'Account\s*Number:?\s*(\d{7,9})', text, re.I)
    return match.group(1) if match else None

VENDOR_ACCOUNTS['Olathe Kansas'] = {
    'has_account': True,
    'format': 'NNNNNNNN',
    'examples': ['99006605'],
    'extract': _extract_olathe_kansas_account
}

def _extract_enevo_account(text: str) -> Optional[str]:
    """Format: NNNNNNNNNN - Example: 4350316561"""
    match = re.search(r'Account\s*Number:?\s*(\d{9,11})', text, re.I)
    return match.group(1) if match else None

VENDOR_ACCOUNTS['Enevo'] = {
    'has_account': True,
    'format': 'NNNNNNNNNN',
    'examples': ['4350316561'],
    'extract': _extract_enevo_account
}

def _extract_sustainable_environmental_management_account(text: str) -> Optional[str]:
    """Format: NNNNNNNNN - Example: 895910001"""
    match = re.search(r'ACCT\.?\s*NO\.?:?\s*(\d{8,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_ACCOUNTS['Sustainable Environmental Management'] = {
    'has_account': True,
    'format': 'NNNNNNNNN',
    'examples': ['895910001'],
    'extract': _extract_sustainable_environmental_management_account
}

def _extract_city_of_mesa_account(text: str) -> Optional[str]:
    """Format: NNNNNNN - Example: 1122193"""
    match = re.search(r'Account\s*Number:?\s*(\d{6,8})', text, re.I)
    return match.group(1) if match else None

VENDOR_ACCOUNTS['City of Mesa'] = {
    'has_account': True,
    'format': 'NNNNNNN',
    'examples': ['1122193'],
    'extract': _extract_city_of_mesa_account
}

def _extract_shawnee_county_solid_waste_account(text: str) -> Optional[str]:
    """Format: NNNNNN - Example: 110458"""
    match = re.search(r'Account\s*Number:?\s*(\d{5,7})', text, re.I)
    return match.group(1) if match else None

VENDOR_ACCOUNTS['Shawnee County Solid Waste'] = {
    'has_account': True,
    'format': 'NNNNNN',
    'examples': ['110458'],
    'extract': _extract_shawnee_county_solid_waste_account
}

def _extract_midwest_disposal_il_account(text: str) -> Optional[str]:
    """Format: NNNNNN - Example: 107512"""
    match = re.search(r'Account\s*Number:?\s*(\d{5,7})', text, re.I)
    return match.group(1) if match else None

VENDOR_ACCOUNTS['Midwest Disposal IL'] = {
    'has_account': True,
    'format': 'NNNNNN',
    'examples': ['107512'],
    'extract': _extract_midwest_disposal_il_account
}

def _extract_dc_waste_account(text: str) -> Optional[str]:
    """Format: NNNNNNN - Example: 3744800"""
    match = re.search(r'Account\s*No:?\s*(\d{6,8})', text, re.I)
    return match.group(1) if match else None

VENDOR_ACCOUNTS['DC Waste'] = {
    'has_account': True,
    'format': 'NNNNNNN',
    'examples': ['3744800'],
    'extract': _extract_dc_waste_account
}

def _extract_nva_services_account(text: str) -> Optional[str]:
    """Format: NNNNNN - Example: 801489"""
    match = re.search(r'Account\s*Number:?\s*(\d{5,7})', text, re.I)
    return match.group(1) if match else None

VENDOR_ACCOUNTS['NVA Services'] = {
    'has_account': True,
    'format': 'NNNNNN',
    'examples': ['801489'],
    'extract': _extract_nva_services_account
}

def _extract_buds_clean_up_service_account(text: str) -> Optional[str]:
    """Format: NNNNNN - Example: 100175"""
    match = re.search(r'Account\s*Number:?\s*(\d{5,7})', text, re.I)
    return match.group(1) if match else None

VENDOR_ACCOUNTS["Bud's Clean Up Service"] = {
    'has_account': True,
    'format': 'NNNNNN',
    'examples': ['100175'],
    'extract': _extract_buds_clean_up_service_account
}

def _extract_impact_environmental_account(text: str) -> Optional[str]:
    """Format: NNNNNNN - Example: 2735911"""
    match = re.search(r'Account\s*Number:?\s*(\d{6,8})', text, re.I)
    return match.group(1) if match else None

VENDOR_ACCOUNTS['Impact Environmental'] = {
    'has_account': True,
    'format': 'NNNNNNN',
    'examples': ['2735911'],
    'extract': _extract_impact_environmental_account
}

def _extract_thompsons_sanitary_service_account(text: str) -> Optional[str]:
    """Format: NNNNN - Example: 03823"""
    match = re.search(r'Account\s*Number:?\s*(\d{4,6})', text, re.I)
    return match.group(1) if match else None

VENDOR_ACCOUNTS["Thompson's Sanitary Service"] = {
    'has_account': True,
    'format': 'NNNNN',
    'examples': ['03823'],
    'extract': _extract_thompsons_sanitary_service_account
}

def _extract_clackamas_garbage_account(text: str) -> Optional[str]:
    """Format: NNNNN - Example: 07061"""
    match = re.search(r'Account\s*Number:?\s*(\d{4,6})', text, re.I)
    return match.group(1) if match else None

VENDOR_ACCOUNTS['Clackamas Garbage'] = {
    'has_account': True,
    'format': 'NNNNN',
    'examples': ['07061'],
    'extract': _extract_clackamas_garbage_account
}

def _extract_davis_disposal_account(text: str) -> Optional[str]:
    """Format: NNNNN - Example: 11940"""
    match = re.search(r'Account\s*Number:?\s*(\d{4,6})', text, re.I)
    return match.group(1) if match else None

VENDOR_ACCOUNTS['Davis Disposal'] = {
    'has_account': True,
    'format': 'NNNNN',
    'examples': ['11940'],
    'extract': _extract_davis_disposal_account
}

def _extract_sutherlin_sanitary_account(text: str) -> Optional[str]:
    """Format: NNNNNNNN - Example: 00008919"""
    match = re.search(r'Account\s*Number:?\s*(\d{7,9})', text, re.I)
    return match.group(1) if match else None

VENDOR_ACCOUNTS['Sutherlin Sanitary'] = {
    'has_account': True,
    'format': 'NNNNNNNN',
    'examples': ['00008919'],
    'extract': _extract_sutherlin_sanitary_account
}

def _extract_iron_mountain_account(text: str) -> Optional[str]:
    """Format: NNNNNNNNN - Example: 323285139"""
    match = re.search(r'Account\s*Number:?\s*(\d{8,10})', text, re.I)
    return match.group(1) if match else None

VENDOR_ACCOUNTS['Iron Mountain'] = {
    'has_account': True,
    'format': 'NNNNNNNNN',
    'examples': ['323285139'],
    'extract': _extract_iron_mountain_account
}

def _extract_waste_pro_oregon_account(text: str) -> Optional[str]:
    """Format: NNNNN - Example: 33622"""
    match = re.search(r'Account\s*Number:?\s*(\d{4,6})', text, re.I)
    return match.group(1) if match else None

VENDOR_ACCOUNTS['Waste Pro Oregon'] = {
    'has_account': True,
    'format': 'NNNNN',
    'examples': ['33622'],
    'extract': _extract_waste_pro_oregon_account
}

def _extract_pratt_recycling_account(text: str) -> Optional[str]:
    """Format: NNNNNN - Example: 283172"""
    match = re.search(r'Customer\s*No:?\s*(\d{5,7})', text, re.I)
    return match.group(1) if match else None

VENDOR_ACCOUNTS['Pratt Recycling'] = {
    'has_account': True,
    'format': 'NNNNNN',
    'examples': ['283172'],
    'extract': _extract_pratt_recycling_account
}

def _extract_virgin_valley_disposal_account(text: str) -> Optional[str]:
    """Format: NNNNN - Example: 11098"""
    match = re.search(r'ACCT\.?\s*NO\.?:?\s*(\d{4,6})', text, re.I)
    return match.group(1) if match else None

VENDOR_ACCOUNTS['Virgin Valley Disposal'] = {
    'has_account': True,
    'format': 'NNNNN',
    'examples': ['11098'],
    'extract': _extract_virgin_valley_disposal_account
}

def _extract_anchorage_solid_waste_account(text: str) -> Optional[str]:
    """Format: NNNNNNNNNN - Example: 1003443000"""
    match = re.search(r'Account\s*No:?\s*(\d{9,11})', text, re.I)
    return match.group(1) if match else None

VENDOR_ACCOUNTS['Anchorage Solid Waste'] = {
    'has_account': True,
    'format': 'NNNNNNNNNN',
    'examples': ['1003443000'],
    'extract': _extract_anchorage_solid_waste_account
}

def _extract_ely_disposal_service_account(text: str) -> Optional[str]:
    """Format: NNNNNN - Example: 118494"""
    match = re.search(r'Account\s*Number:?\s*(\d{5,7})', text, re.I)
    return match.group(1) if match else None

VENDOR_ACCOUNTS['Ely Disposal Service'] = {
    'has_account': True,
    'format': 'NNNNNN',
    'examples': ['118494'],
    'extract': _extract_ely_disposal_service_account
}

def _extract_dans_sanitation_account(text: str) -> Optional[str]:
    """Format: NNNNNN - Example: 110779"""
    match = re.search(r'Account\s*Number:?\s*(\d{5,7})', text, re.I)
    return match.group(1) if match else None

VENDOR_ACCOUNTS["Dan's Sanitation"] = {
    'has_account': True,
    'format': 'NNNNNN',
    'examples': ['110779'],
    'extract': _extract_dans_sanitation_account
}

def _extract_gresham_sanitary_service_account(text: str) -> Optional[str]:
    """Format: NNNNNNN - Example: 2495938"""
    match = re.search(r'Account\s*Number:?\s*(\d{6,8})', text, re.I)
    return match.group(1) if match else None

VENDOR_ACCOUNTS['Gresham Sanitary Service'] = {
    'has_account': True,
    'format': 'NNNNNNN',
    'examples': ['2495938'],
    'extract': _extract_gresham_sanitary_service_account
}

def _extract_north_lincoln_sanitary_account(text: str) -> Optional[str]:
    """Format: NNNNN - Example: 19223"""
    match = re.search(r'Account\s*Number:?\s*(\d{4,6})', text, re.I)
    return match.group(1) if match else None

VENDOR_ACCOUNTS['North Lincoln Sanitary'] = {
    'has_account': True,
    'format': 'NNNNN',
    'examples': ['19223'],
    'extract': _extract_north_lincoln_sanitary_account
}

def _extract_walker_garbage_and_recycling_account(text: str) -> Optional[str]:
    """Format: NNNNNNN - Example: 1355264"""
    match = re.search(r'Account\s*Number:?\s*(\d{6,8})', text, re.I)
    return match.group(1) if match else None

VENDOR_ACCOUNTS['Walker Garbage and Recycling'] = {
    'has_account': True,
    'format': 'NNNNNNN',
    'examples': ['1355264'],
    'extract': _extract_walker_garbage_and_recycling_account
}

def _extract_shamrock_waste_account(text: str) -> Optional[str]:
    """Format: NNNNNN - Example: 100023"""
    match = re.search(r'Account\s*Number:?\s*(\d{5,7})', text, re.I)
    return match.group(1) if match else None

VENDOR_ACCOUNTS['Shamrock Waste'] = {
    'has_account': True,
    'format': 'NNNNNN',
    'examples': ['100023'],
    'extract': _extract_shamrock_waste_account
}

def _extract_industrial_waste_salvage_account(text: str) -> Optional[str]:
    """Format: NNNNNN - Example: 043201"""
    match = re.search(r'Customer\s*No:?\s*(\d{5,7})', text, re.I)
    return match.group(1) if match else None

VENDOR_ACCOUNTS['Industrial Waste & Salvage'] = {
    'has_account': True,
    'format': 'NNNNNN',
    'examples': ['043201'],
    'extract': _extract_industrial_waste_salvage_account
}

def _extract_dans_r_us_sanitation_account(text: str) -> Optional[str]:
    """Format: NNNNNN - Example: 105932"""
    match = re.search(r'Account\s*Number:?\s*(\d{5,7})', text, re.I)
    return match.group(1) if match else None

VENDOR_ACCOUNTS["Dan's R Us Sanitation"] = {
    'has_account': True,
    'format': 'NNNNNN',
    'examples': ['105932'],
    'extract': _extract_dans_r_us_sanitation_account
}

def _extract_cb_sanitary_account(text: str) -> Optional[str]:
    """Format: NNNNN - Example: 19757"""
    match = re.search(r'Account\s*Number:?\s*(\d{4,6})', text, re.I)
    return match.group(1) if match else None

VENDOR_ACCOUNTS['C & B Sanitary'] = {
    'has_account': True,
    'format': 'NNNNN',
    'examples': ['19757'],
    'extract': _extract_cb_sanitary_account
}

def _extract_city_of_redwood_account(text: str) -> Optional[str]:
    """Format: NNNNNNN - Example: 1017008"""
    match = re.search(r'Account\s*No:?\s*(\d{6,8})', text, re.I)
    return match.group(1) if match else None

VENDOR_ACCOUNTS['City of Redwood'] = {
    'has_account': True,
    'format': 'NNNNNNN',
    'examples': ['1017008'],
    'extract': _extract_city_of_redwood_account
}

# V8 AUTO-GENERATED EXTRACTORS - Batch 3 (9 more vendors)

def _extract_suburban_disposal_account(text: str) -> Optional[str]:
    """Format: NNNNNN - Example: 088140"""
    match = re.search(r'Account\s*No:?\s*(\d{5,7})', text, re.I)
    return match.group(1) if match else None

VENDOR_ACCOUNTS['Suburban Disposal'] = {
    'has_account': True,
    'format': 'NNNNNN',
    'examples': ['088140'],
    'extract': _extract_suburban_disposal_account
}

def _extract_wayne_county_utah_account(text: str) -> Optional[str]:
    """Format: NNN - Example: 348"""
    match = re.search(r'Customer\s*No:?\s*(\d{2,4})', text, re.I)
    return match.group(1) if match else None

VENDOR_ACCOUNTS['Wayne County Utah'] = {
    'has_account': True,
    'format': 'NNN',
    'examples': ['348'],
    'extract': _extract_wayne_county_utah_account
}

def _extract_recycling_services_of_florida_account(text: str) -> Optional[str]:
    """Format: NNNN - Example: 2878"""
    match = re.search(r'Customer\s*No:?\s*(\d{3,5})', text, re.I)
    return match.group(1) if match else None

VENDOR_ACCOUNTS['Recycling Services of Florida'] = {
    'has_account': True,
    'format': 'NNNN',
    'examples': ['2878'],
    'extract': _extract_recycling_services_of_florida_account
}

def _extract_city_of_oakland_park_account(text: str) -> Optional[str]:
    """Format: NNNNNNNNNN - Example: 1098322802"""
    match = re.search(r'Customer\s*No:?\s*(\d{8,12})', text, re.I)
    return match.group(1) if match else None

VENDOR_ACCOUNTS['City of Oakland Park'] = {
    'has_account': True,
    'format': 'NNNNNNNNNN',
    'examples': ['1098322802'],
    'extract': _extract_city_of_oakland_park_account
}

def _extract_mars_city_of_beatrice_account(text: str) -> Optional[str]:
    """Format: NNNN - Example: 6704"""
    match = re.search(r'Customer\s*No:?\s*(\d{3,5})', text, re.I)
    return match.group(1) if match else None

VENDOR_ACCOUNTS['MARS City of Beatrice'] = {
    'has_account': True,
    'format': 'NNNN',
    'examples': ['6704'],
    'extract': _extract_mars_city_of_beatrice_account
}

def _extract_lincoln_county_solid_waste_account(text: str) -> Optional[str]:
    """Format: NNNNNN - Example: 706113"""
    match = re.search(r'Customer\s*No:?\s*(\d{5,7})', text, re.I)
    return match.group(1) if match else None

VENDOR_ACCOUNTS['Lincoln County Solid Waste'] = {
    'has_account': True,
    'format': 'NNNNNN',
    'examples': ['706113'],
    'extract': _extract_lincoln_county_solid_waste_account
}

def _extract_miller_waste_systems_account(text: str) -> Optional[str]:
    """Format: NNN - Example: 115"""
    match = re.search(r'Customer\s*No:?\s*(\d{2,4})', text, re.I)
    return match.group(1) if match else None

VENDOR_ACCOUNTS['Miller Waste Systems'] = {
    'has_account': True,
    'format': 'NNN',
    'examples': ['115'],
    'extract': _extract_miller_waste_systems_account
}

def _extract_midwest_paper_account(text: str) -> Optional[str]:
    """Format: NNNN - Example: 3799"""
    match = re.search(r'Customer\s*No:?\s*(\d{3,5})', text, re.I)
    return match.group(1) if match else None

VENDOR_ACCOUNTS['Midwest Paper'] = {
    'has_account': True,
    'format': 'NNNN',
    'examples': ['3799'],
    'extract': _extract_midwest_paper_account
}

def _extract_salandro_refuse_account(text: str) -> Optional[str]:
    """Format: NNNNNNN - Example: 0001500"""
    match = re.search(r'Billing\s*#:?\s*(\d{5,8})', text, re.I)
    return match.group(1) if match else None

VENDOR_ACCOUNTS['Salandro Refuse'] = {
    'has_account': True,
    'format': 'NNNNNNN',
    'examples': ['0001500'],
    'extract': _extract_salandro_refuse_account
}

# V8 AUTO-GENERATED EXTRACTORS - Batch 4 (Account_dash format vendors)

def _extract_southwest_sanitation_account(text: str) -> Optional[str]:
    """Format: NN-NNNNN - Example: 01-21286"""
    match = re.search(r'Account\s*#?:?\s*(\d{2}-\d{5,6})', text, re.I)
    return match.group(1) if match else None

VENDOR_ACCOUNTS['Southwest Sanitation'] = {
    'has_account': True,
    'format': 'NN-NNNNN',
    'examples': ['01-21286'],
    'extract': _extract_southwest_sanitation_account
}

def _extract_syracuse_haulers_account(text: str) -> Optional[str]:
    """Format: NN-NNNNNN - Example: 10-289586"""
    match = re.search(r'Account\s*#?:?\s*(\d{2}-\d{6,7})', text, re.I)
    return match.group(1) if match else None

VENDOR_ACCOUNTS['Syracuse Haulers'] = {
    'has_account': True,
    'format': 'NN-NNNNNN',
    'examples': ['10-289586'],
    'extract': _extract_syracuse_haulers_account
}

def _extract_elecke_account(text: str) -> Optional[str]:
    """Format: NN-NNNNNN - Example: 01-815320"""
    match = re.search(r'Account\s*#?:?\s*(\d{2}-\d{6,7})', text, re.I)
    return match.group(1) if match else None

VENDOR_ACCOUNTS['Elecke'] = {
    'has_account': True,
    'format': 'NN-NNNNNN',
    'examples': ['01-815320'],
    'extract': _extract_elecke_account
}

def _extract_waste_eliminator_account(text: str) -> Optional[str]:
    """Format: NN-NNNNN - Example: 01-12318"""
    match = re.search(r'Account\s*#?:?\s*(\d{2}-\d{5,6})', text, re.I)
    return match.group(1) if match else None

VENDOR_ACCOUNTS['Waste Eliminator'] = {
    'has_account': True,
    'format': 'NN-NNNNN',
    'examples': ['01-12318'],
    'extract': _extract_waste_eliminator_account
}

def _extract_laveine_sanitation_account(text: str) -> Optional[str]:
    """Format: NN-NNNNN - Example: 01-12374"""
    match = re.search(r'Account\s*#?:?\s*(\d{2}-\d{5,6})', text, re.I)
    return match.group(1) if match else None

VENDOR_ACCOUNTS['LaVeine Sanitation'] = {
    'has_account': True,
    'format': 'NN-NNNNN',
    'examples': ['01-12374'],
    'extract': _extract_laveine_sanitation_account
}

def _extract_res_waste_account(text: str) -> Optional[str]:
    """Format: NN-NNNNN - Example: 01-55912"""
    match = re.search(r'Account\s*#?:?\s*(\d{2}-\d{5,6})', text, re.I)
    return match.group(1) if match else None

VENDOR_ACCOUNTS['RES Waste'] = {
    'has_account': True,
    'format': 'NN-NNNNN',
    'examples': ['01-55912'],
    'extract': _extract_res_waste_account
}

def _extract_southern_oregon_sanitation_account(text: str) -> Optional[str]:
    """Format: NN-NNNNNNN - Example: 01-0075235"""
    match = re.search(r'Account\s*#?:?\s*(\d{2}-\d{7,8})', text, re.I)
    return match.group(1) if match else None

VENDOR_ACCOUNTS['Southern Oregon Sanitation'] = {
    'has_account': True,
    'format': 'NN-NNNNNNN',
    'examples': ['01-0075235'],
    'extract': _extract_southern_oregon_sanitation_account
}

def _extract_tahoe_basin_container_account(text: str) -> Optional[str]:
    """Format: NN-NNNNN - Example: 50-11140"""
    match = re.search(r'Account\s*#?:?\s*(\d{2}-\d{5,6})', text, re.I)
    return match.group(1) if match else None

VENDOR_ACCOUNTS['Tahoe Basin Container'] = {
    'has_account': True,
    'format': 'NN-NNNNN',
    'examples': ['50-11140'],
    'extract': _extract_tahoe_basin_container_account
}

def _extract_sweetland_account(text: str) -> Optional[str]:
    """Format: NN-NNNNN - Example: 10-21420"""
    match = re.search(r'Account\s*#?:?\s*(\d{2}-\d{5,6})', text, re.I)
    return match.group(1) if match else None

VENDOR_ACCOUNTS['Sweetland'] = {
    'has_account': True,
    'format': 'NN-NNNNN',
    'examples': ['10-21420'],
    'extract': _extract_sweetland_account
}

def _extract_ljp_waste_account(text: str) -> Optional[str]:
    """Format: NN-NNNNNNN - Example: 10-7532277"""
    match = re.search(r'Account\s*#?:?\s*(\d{2}-\d{7,8})', text, re.I)
    return match.group(1) if match else None

VENDOR_ACCOUNTS['LJP Waste'] = {
    'has_account': True,
    'format': 'NN-NNNNNNN',
    'examples': ['10-7532277'],
    'extract': _extract_ljp_waste_account
}

def _extract_city_of_henagar_account(text: str) -> Optional[str]:
    """Format: NN-NNNNN - Example: 10-49519"""
    match = re.search(r'Account\s*#?:?\s*(\d{2}-\d{5,6})', text, re.I)
    return match.group(1) if match else None

VENDOR_ACCOUNTS['City of Henagar'] = {
    'has_account': True,
    'format': 'NN-NNNNN',
    'examples': ['10-49519'],
    'extract': _extract_city_of_henagar_account
}

def _extract_arrow_waste_account(text: str) -> Optional[str]:
    """Format: NN-NNNNNN - Example: 10-104710"""
    match = re.search(r'Account\s*#?:?\s*(\d{2}-\d{6,7})', text, re.I)
    return match.group(1) if match else None

VENDOR_ACCOUNTS['Arrow Waste'] = {
    'has_account': True,
    'format': 'NN-NNNNNN',
    'examples': ['10-104710'],
    'extract': _extract_arrow_waste_account
}

# V8 AUTO-GENERATED EXTRACTORS - Batch 5 (Account_dash_space and alphanum patterns)

def _extract_at_disposal_account(text: str) -> Optional[str]:
    """Format: NN-NNNN N - Example: 01-4038 5"""
    match = re.search(r'Account\s*No\.?\s*(\d{2}-\d{4}\s*\d)', text, re.I)
    if match:
        return match.group(1).replace(' ', '')
    return None

VENDOR_ACCOUNTS['AT Disposal'] = {
    'has_account': True,
    'format': 'NN-NNNNN',
    'examples': ['01-40385'],
    'extract': _extract_at_disposal_account
}

def _extract_crane_rolloff_account(text: str) -> Optional[str]:
    """Format: NN-NNNN N - Example: 01-6680 2"""
    match = re.search(r'Account\s*No\.?\s*(\d{2}-\d{4}\s*\d)', text, re.I)
    if match:
        return match.group(1).replace(' ', '')
    return None

VENDOR_ACCOUNTS['Crane Roll-Off'] = {
    'has_account': True,
    'format': 'NN-NNNNN',
    'examples': ['01-66802'],
    'extract': _extract_crane_rolloff_account
}

def _extract_kuerths_disposal_account(text: str) -> Optional[str]:
    """Format: NN-NNNN N - Example: 01-3383 6"""
    match = re.search(r'Account\s*No\.?\s*(\d{2}-\d{4}\s*\d)', text, re.I)
    if match:
        return match.group(1).replace(' ', '')
    return None

VENDOR_ACCOUNTS["Kuerth's Disposal"] = {
    'has_account': True,
    'format': 'NN-NNNNN',
    'examples': ['01-33836'],
    'extract': _extract_kuerths_disposal_account
}

def _extract_solomon_container_service_account(text: str) -> Optional[str]:
    """Format: NN-NNNN N - Example: 01-4038 5"""
    match = re.search(r'Account\s*No\.?\s*(\d{2}-\d{4}\s*\d)', text, re.I)
    if match:
        return match.group(1).replace(' ', '')
    return None

VENDOR_ACCOUNTS['Solomon Container Service'] = {
    'has_account': True,
    'format': 'NN-NNNNN',
    'examples': ['01-40385'],
    'extract': _extract_solomon_container_service_account
}

def _extract_ma_sanitation_account(text: str) -> Optional[str]:
    """Format: NN-NNNN - Example: 10-2666"""
    match = re.search(r'Account\s*No\.?\s*(\d{2}-\d{4,6})', text, re.I)
    return match.group(1) if match else None

VENDOR_ACCOUNTS['MA Sanitation'] = {
    'has_account': True,
    'format': 'NN-NNNN',
    'examples': ['10-2666'],
    'extract': _extract_ma_sanitation_account
}

def _extract_western_kane_county_account(text: str) -> Optional[str]:
    """Format: CNNNN - Example: C1220"""
    match = re.search(r'Account\s*#\s*([A-Z]\d{4,6})', text, re.I)
    return match.group(1) if match else None

VENDOR_ACCOUNTS['Western Kane County'] = {
    'has_account': True,
    'format': 'CNNNN',
    'examples': ['C1220'],
    'extract': _extract_western_kane_county_account
}


# V8 Final - Last 6 vendors
def _extract_community_waste_account(text: str) -> Optional[str]:
    """Community Waste - Multiple formats
    Format 1: NN-NNNNNN N (Customer Number) - 10-143288 8
    Format 2: NNNNNN-NNN (ACCOUNT #) - 107441-109
    """
    lines = text.replace('\\n', '\n').split('\n')

    # Pattern 1: ACCOUNT # header, value in nearby lines (NNNNNN-NNN format)
    for i, line in enumerate(lines):
        if re.match(r'^ACCOUNT\s*#\s*$', line, re.I):
            for j in range(i+1, min(i+4, len(lines))):
                val = lines[j].strip()
                m = re.match(r'^(\d{6}-\d{3})$', val)
                if m:
                    return m.group(1)

    # Pattern 2: Customer Number header, value in nearby lines (NN-NNNNNN N format)
    for i, line in enumerate(lines):
        if 'customer number' in line.lower():
            for j in range(i, min(i+8, len(lines))):
                val = lines[j].strip()
                m = re.match(r'^(\d{2}-\d{6}\s*\d)$', val)
                if m:
                    return m.group(1).strip()

    # Pattern 3: Inline formats
    match = re.search(r'ACCOUNT\s*#[:\s]*(\d{6}-\d{3})', text, re.I)
    if match:
        return match.group(1)
    match = re.search(r'Customer\s*Number[:\s]*(\d{2}-\d{6}\s*\d)', text, re.I)
    if match:
        return match.group(1).strip()

    return None

VENDOR_ACCOUNTS['Community Waste'] = {
    'has_account': True,
    'format': 'NN-NNNNNN N or NNNNNN-NNN',
    'examples': ['10-143288 8', '107441-109'],
    'extract': _extract_community_waste_account
}


def _extract_recology_account(text: str) -> Optional[str]:
    """Recology - 10-digit account number"""
    match = re.search(r'Account\s*Number[:\s]*(\d{10})', text, re.I)
    return match.group(1) if match else None

VENDOR_ACCOUNTS['Recology'] = {
    'has_account': True,
    'format': 'NNNNNNNNNN',
    'examples': ['8100237266'],
    'extract': _extract_recology_account
}


def _extract_star_waste_account(text: str) -> Optional[str]:
    """Star Waste - Account number after ACCOUNT NUMBER label"""
    lines = text.replace('\\n', '\n').split('\n')
    for i, line in enumerate(lines[:-1]):
        if 'ACCOUNT NUMBER' in line.upper():
            val = lines[i+1].strip()
            if re.match(r'^[\dA-Z-]+$', val) and len(val) >= 4:
                return val
    match = re.search(r'ACCOUNT\s*NUMBER[:\s]*([A-Z0-9-]+)', text, re.I)
    return match.group(1) if match else None

VENDOR_ACCOUNTS['Star Waste'] = {
    'has_account': True,
    'format': 'varies',
    'examples': [],
    'extract': _extract_star_waste_account
}


def _extract_recology(text: str) -> Optional[str]:
    """Recology - Multiple account formats
    Format: 10 digit account number (8100XXXXXX pattern common)
    Examples: 8100237266, 8100236642, 1080914879
    """
    lines = text.replace('\\n', '\n').split('\n')

    # Pattern 1: "Statement Account" / "Number Number" / "NNNN NNNN" format
    for i, line in enumerate(lines[:-2]):
        if 'account' in line.lower():
            if i+1 < len(lines) and 'number' in lines[i+1].lower():
                # Check next few lines for two numbers (statement# account#)
                for j in range(i+2, min(i+5, len(lines))):
                    # Match two 10+ digit numbers, account is second one starting with 81
                    matches = re.findall(r'\b(\d{10,13})\b', lines[j])
                    if len(matches) >= 2:
                        for m in matches:
                            if m.startswith('81'):
                                return m
                    # Single 10-digit number
                    elif len(matches) == 1 and (matches[0].startswith('81') or matches[0].startswith('10')):
                        return matches[0]

    # Pattern 2: "Account" then "Number" on separate lines, value follows
    for i, line in enumerate(lines[:-2]):
        if line.strip().lower() == 'account':
            if i+1 < len(lines) and lines[i+1].strip().lower() == 'number':
                for j in range(i+2, min(i+6, len(lines))):
                    matches = re.findall(r'\b(\d{10})\b', lines[j])
                    for m in matches:
                        if m.startswith('81') or m.startswith('10'):
                            return m

    # Pattern 3: Account Number: columnar (older format)
    for i, line in enumerate(lines):
        if 'account number' in line.lower() and ':' in line:
            for j in range(i, min(i+6, len(lines))):
                val = lines[j].strip()
                if re.match(r'^\d{9,10}$', val):
                    return val

    # Pattern 4: Inline format
    match = re.search(r'Account\s*Number[:\s]*(\d{9,10})', text, re.I)
    if match:
        return match.group(1)

    return None

VENDOR_ACCOUNTS['Recology'] = {
    'has_account': True,
    'format': 'NNNNNNNNNN',
    'examples': ['8100237266', '1080914879'],
    'extract': _extract_recology
}


def _extract_arrowaste(text: str) -> Optional[str]:
    """Arrowaste - Cust. # with check digit format
    Format: NN-NNNNN(N) N (district-account check_digit)
    Examples: 91-255400 4, 91-53730 8
    """
    lines = text.replace('\\n', '\n').split('\n')

    # Pattern 1: Cust. # on one line, value on next
    for i, line in enumerate(lines[:-1]):
        if re.match(r'^Cust\.?\s*#\s*$', line, re.I):
            val = lines[i+1].strip()
            m = re.match(r'^(\d{2}-\d{5,6}\s*\d)$', val)
            if m:
                return m.group(1)

    # Pattern 2: Inline format
    match = re.search(r'Cust\.?\s*#\s*(\d{2}-\d{5,6}\s*\d)', text, re.I)
    if match:
        return match.group(1).strip()

    return None

VENDOR_ACCOUNTS['Arrowaste'] = {
    'has_account': True,
    'format': 'NN-NNNNN(N) N',
    'examples': ['91-255400 4', '91-53730 8'],
    'extract': _extract_arrowaste
}


# ============================================================
# V10 ADDITIONS - January 2026 Account Linkage Validation
# Fixed vendors incorrectly in NO_ACCOUNT list
# ============================================================

def _extract_fl_construction(text: str) -> Optional[str]:
    """F & L Construction - CUSTOMER NO. format
    OCR layout: value appears BEFORE the label on previous line
    Examples: 2203, 2217, 1667
    """
    lines = text.replace('\\n', '\n').split('\n')
    for i, line in enumerate(lines):
        if 'CUSTOMER NO' in line.upper():
            # Check previous line for the value
            if i > 0:
                prev = lines[i-1].strip()
                if re.match(r'^\d{4,5}$', prev):
                    return prev
    return None

VENDOR_ACCOUNTS['F & L Construction'] = {
    'has_account': True,
    'format': 'NNNN+',
    'examples': ['2203', '2217', '1667'],
    'extract': _extract_fl_construction
}


def _extract_goods_disposal(text: str) -> Optional[str]:
    """Good's Disposal - CUSTOMER NO. format
    OCR layout: columnar - headers on lines 8-13, values on lines 14-18
    CUSTOMER NO. header at line 11 corresponds to value at line 17
    Examples: 79544, 23138
    """
    lines = text.replace('\\n', '\n').split('\n')
    for i, line in enumerate(lines):
        if 'CUSTOMER NO' in line.upper():
            # Columnar format: value is 6 lines after header
            for offset in [6, 5, 7, 4, 8]:  # Try different offsets
                if i + offset < len(lines):
                    val = lines[i + offset].strip()
                    if re.match(r'^\d{5,6}$', val):
                        return val
    return None

VENDOR_ACCOUNTS["Good's Disposal"] = {
    'has_account': True,
    'format': 'NNNNN+',
    'examples': ['79544', '23138'],
    'extract': _extract_goods_disposal
}


def _extract_total_disposal_inc(text: str) -> Optional[str]:
    """Total Disposal Inc - CUSTOMER NO. format
    OCR layout: value on next line after label
    Examples: 007692
    """
    lines = text.replace('\\n', '\n').split('\n')
    for i, line in enumerate(lines):
        if 'CUSTOMER NO' in line.upper():
            # Check next line for the value
            if i + 1 < len(lines):
                val = lines[i+1].strip()
                if re.match(r'^\d{6}$', val):
                    return val
    return None

VENDOR_ACCOUNTS['Total Disposal Inc'] = {
    'has_account': True,
    'format': 'NNNNNN+',
    'examples': ['007692'],
    'extract': _extract_total_disposal_inc
}


def _extract_kc_disposal(text: str) -> Optional[str]:
    """KC Disposal - CUSTOMER NUMBER format
    OCR layout: value on next line (format: NN-NNNNNN N)
    Examples: 02-614790, 02-575462 5
    """
    lines = text.replace('\\n', '\n').split('\n')
    for i, line in enumerate(lines):
        if 'CUSTOMER NUMBER' in line.upper():
            # Check next line for the value
            if i + 1 < len(lines):
                val = lines[i+1].strip()
                if re.match(r'^\d{2}-\d{6}(\s*\d)?$', val):
                    return val
    return None

VENDOR_ACCOUNTS['KC Disposal'] = {
    'has_account': True,
    'format': 'NN-NNNNNN',
    'examples': ['02-614790'],
    'extract': _extract_kc_disposal
}


def _extract_bliss_environmental(text: str) -> Optional[str]:
    """Bliss Environmental - ACCOUNT NO. format (12 digits)
    Examples: 401980196427
    """
    match = re.search(r'ACCOUNT\s*(?:NO\.?|NUMBER|#)\s*[:\s]*(\d{12})', text, re.I)
    if match:
        return match.group(1)
    return None

VENDOR_ACCOUNTS['Bliss Environmental'] = {
    'has_account': True,
    'format': 'NNNNNNNNNNNN',
    'examples': ['401980196427'],
    'extract': _extract_bliss_environmental
}


def _extract_bp_trucking(text: str) -> Optional[str]:
    """BP Trucking - CUSTOMER NUMBER format
    OCR layout: value on next line
    Examples: 14805
    """
    lines = text.replace('\\n', '\n').split('\n')
    for i, line in enumerate(lines):
        if 'CUSTOMER NUMBER' in line.upper():
            # Check next line for the value
            if i + 1 < len(lines):
                val = lines[i+1].strip()
                if re.match(r'^\d{5}$', val):
                    return val
    return None

VENDOR_ACCOUNTS['BP Trucking'] = {
    'has_account': True,
    'format': 'NNNNN+',
    'examples': ['14805'],
    'extract': _extract_bp_trucking
}


def _extract_mills_brothers(text: str) -> Optional[str]:
    """Mills Brothers - ACCT/ACCOUNT format
    Examples: 358105
    """
    match = re.search(r'(?:ACCOUNT|ACCT)\.?\s*(?:NO\.?|#)?\s*[:\s]*(\d{6})', text, re.I)
    if match:
        return match.group(1)
    return None

VENDOR_ACCOUNTS['Mills Brothers'] = {
    'has_account': True,
    'format': 'NNNNNN',
    'examples': ['358105'],
    'extract': _extract_mills_brothers
}


NO_ACCOUNT_VENDORS = [
    # V8 Final - invoice-only vendors
    'Diamond Disposal',
    'Parish Disposal',
    'Area Refuse',
    'Standard Waste',      # Scale tickets
    'Redbox+',            # Invoice-based
    'CRI Curbside',       # Invoice-based
    'Rocky Ridge',        # Invoice-based
    'Specific Waste',     # Manifests/certificates
    'Boyas Recycling',    # Invoice-based  
    'Las Vegas Recycling', # Job numbers
    'Howard Disposal',    # Invoice-based
    'Five Star Waste',    # Invoice-based
    'Wise Environmental', # No standard account
    'Trash Taxi',         # TrashBilling ID (not account)
    'ACES Disposal',      # TrashBilling ID  
    'RDT Inc',            # TrashBilling ID
    'Heavenly Trash',     # TrashBilling ID
    'Solid Waste Authority', # Ticket-based
    'Grizzly Disposal',   # TrashBilling ID
    # V4 additions
    'Advance Machine & Hydraulic',  # PO/Invoice based
    'Green Guys',         # Invoice-based, order numbers
    # V5 additions - Tranche 1
    'Becker360',          # Order/Invoice based only
    'Pete & Pete',        # Service tickets, PO numbers
    # V5 additions - Tranche 2
    'Conigliaro',         # Invoice/WO based (recycling services)
    'D Crescio Trucking', # Uses customer name as ID, not number
    'Premier Waste',      # Invoice-based (no consistent account format)
    # V6 additions - Account Linkage Project
    'North Iredell Sanitation',  # Invoice-based only (no account number on invoices)
    # V7 additions - January 2026 Analysis
    'Wompost',              # Invoice-based (821 invoices)
    'Stryker Environmental', # Invoice-based (714 invoices) - job/haul based
    'Community Disposal',   # Invoice-based (274 invoices)
    'Walker Lake Disposal', # Invoice-based (200 invoices)
    'Curbside',            # Invoice-based (198 invoices)
    'Corporate Services Consultants', # Invoice-based (167 invoices)
    'Conex Recycling',     # Invoice-based (153 invoices)
    'All Metals Recycling', # Invoice-based (139 invoices)
    'Pennohio',            # Invoice-based (135 invoices)
    'Roosevelt UT',        # Invoice-based (135 invoices)
    'Total Reclaim',       # Invoice-based (134 invoices)
    'AAA Disposal Service', # Invoice-based (129 invoices)
    'Southern Illinois Waste', # Invoice-based (128 invoices)
    'AG Logistics',        # Invoice-based (118 invoices)
    'River Parish Disposal', # Invoice-based (117 invoices)
    'E.J. Harrison & Sons', # Invoice-based (112 invoices)
    'Specialty Pallet',    # Invoice/Sales Order based (162 invoices)
    'Clean Slate',         # Invoice-based/receipt format (171 invoices)
    'Dependable Sanitation', # TrashBilling (142 invoices)
    'Hill Country Waste',  # TrashBilling (138 invoices)
    'Bruin Waste Management', # Invoice-based (137 invoices)
    'Texas Pride Disposal', # Invoice-based (134 invoices)
    'City of Jackson',     # Invoice-based (130 invoices)
    'Waste Path',          # Invoice-based (128 invoices)
    'Southern Sanitation', # Invoice-based (128 invoices)
    # V8 additions - January 2026 Bulk Analysis (160 vendors without account keywords)
    '4G Futures',
    'A&L Compaction',
    'A-1 Disposal',
    'A-1 Little John',
    'AAA Trash Service',
    'AB-8 Waste Solutions',
    'Accurate Paper Recycling',
    'Ace Equipment Company',
    'Action Trucking',
    'All Florida Scrap Metals',
    'Allied Recycling',
    'Always Green Recycling',
    'American Resource Management',
    'Appalachian Waste Management',
    'Arg Services',
    'Armor Environmental',
    'B&L Disposal',
    'BTS Inc',
    'Becker Complete',
    'Blue Ridge Waste',
    'Bower Disposal',
    'Brew Crew Environmental',
    'Brookings Dumpster Service',
    'C&S Disposal',
    'Carrier Container',
    'Central Valley Disposal',
    'Certified Enterprises',
    'Chambersburg Waste Paper',
    'City of Bardstown',
    'City of Lebanon',
    'City of Sulphur Springs',
    'Civicorps Recycling',
    'Clarke Waste Solutions',
    "Cliff's Commercial Trash",
    'Community Sanitation',
    'DKMM Solid Waste',
    'Darob',
    'Desert Green Disposal',
    'Dunham',
    'Eagle Equipment Service 1',
    'EarthSavers',
    'Edward Arnold Scrap Processors',
    'Enviromax Recycling',
    'Expert Transportation',
    'Express Disposal',
    'Family Trash Service',
    'Federal Recycling & Waste Solutions',
    "Ferrell's Disposal",
    'Fiber Services',
    'Flash Trash',
    'Franklin Disposal',
    'Franklin Pallet',
    'GTX Gainsborough Waste',
    'Garden Isle Disposal',
    'Gear For Waste',
    'Geodom Carting',
    'Gibson Truck Service',
    'Going Green Recycle',
    'Golden Valley Disposal',
    'Grand Rapids Iron',
    'Graybill Equipment & Repair',
    'Green Guy Recycling',
    'Green OBKY',
    'Green Planet 21',
    'Grogan Waste',
    "Guido's Services",
    'H & H Sanitation',
    'HEM Service Company',
    'Happen Ventures',
    'Helgerson Property Maintenance',
    'Hillside Solutions',
    'Hilltopper Refuse',
    'Hopper Disposal',
    'Hoss Disposal',
    'Hughes Waste Haulers',
    'Island Recycling',
    'Island Refuse',
    'J & B Disposal',
    'J&T Environmental',
    'JDog Junk Removal',
    'Junk Solutions',
    "Kadinger's",
    "Kings Roll-Off",
    'Kohlmorgan Hauling',
    "Kurtzman's Sanitation",
    'LK Specialties',
    'Lance Refuse',
    'Lemhi Sanitation',
    'Local Waste Solution',
    'Long Beach Container',
    'MCS Midwest',
    'MSC Industries',
    "Mac's Wood Products",
    'Maguire Equipment',
    'Mavilyn Industries',
    'McGree Trucking',
    'Metalico Youngstown',
    'Metech Recycling',
    'Miami Waste Paper',
    'Miedema Sanitation',
    'Mike Spano & Sons',
    'Miller and Sons Disposal',
    'Mogford Metals',
    'Montgomery County Environmental',
    'Moon Companies',
    'Mulberry Ventures',
    'My Green Michigan',
    'NW Dumpsters',
    'Native Dynamics',
    'North Country Disposal',
    'Nowrush Recycling',
    'Oak Disposal Services',
    'Ogborne Hauling',
    'Old West Disposal',
    'Omni',
    'Pak-Rite Rentals',
    'Porter Trash',
    'Post Environmental Services',
    'Potties for the Rockies',
    'Prolex Compacting',
    'Pyles Demolition Recycling',
    'Recycling Center of North Dakota',
    'Reddy Rentals',
    'Reed Maintenance',
    'Revolution Recycling',
    'Reworld',
    'RightAway RollOff',
    'Roll-Off Chick',
    'Royal Oak Recycling',
    'SOS Waste Disposal',
    'Sage Disposal',
    'Sanitation One',
    'Scraps Compost',
    'Self Recycling',
    'Serious Sanitation',
    'Shred360',
    'Smoky Mountain Waste',
    'Snake River Dispose-All',
    'Sonoco Recycling',
    'South Plains Waste',
    'Speedy Dump',
    'Standing Rock Sanitation',
    'Styro Recycle',
    'Sunny Trash Hauling',
    'Sunrise Sanitation Service',
    'TNR Hauling',
    'Timberline LLC',
    'Toro Waste',
    'Treasure Coast Recycling',
    'Ultimate Specialties',
    'WFT Waste',
    'Wampler Services',
    'Waste Collection Services',
    'Waste Express',
    'Waste Harmonics',
    'WasteVision',
    "Wayn-O's Disposal Service",
    'Wemiga Waste',
    'William Sullivan',
    'Zero Waste',
    # V8 Batch 3 - Additional invoice-only vendors
    "Cliff's Commercial Trash",
    'Community Sanitation',
    'DKMM Solid Waste',
    'Darob',
    'Desert Green Disposal',
    'Dunham',
    'Eagle Equipment Service 1',
    'EarthSavers',
    'Edward Arnold Scrap Processors',
    'Enviromax Recycling',
    'Expert Transportation',
    'Express Disposal',
    'Family Trash Service',
    'Federal Recycling & Waste Solutions',
    "Ferrell's Disposal",
    "Guido's Services",
    'H & H Sanitation',
    'HEM Service Company',
    'Happen Ventures',
    'Helgerson Property Maintenance',
    'Hillside Solutions',
    'Hilltopper Refuse',
    'Hopper Disposal',
    'Hoss Disposal',
    'Hughes Waste Haulers',
    'Island Recycling',
    'Island Refuse',
    'J & B Disposal',
    'J&T Environmental',
    'JDog Junk Removal',
    'Junk Solutions',
    "Kadinger's",
    "Kings Roll-Off",
    "Kurtzman's Sanitation",
    'LK Specialties',
    'Lance Refuse',
    'Lemhi Sanitation',
    'Local Waste Solution',
    'Long Beach Container',
    'MCS Midwest',
    'MSC Industries',
    "Mac's Wood Products",
    # V8 Batch 3 - TrashBilling Customer_Info vendors (payment receipts, not accounts)
    'Norris Sanitation',
    'Brothers Disposal',
    'OTHER',
    'Myers Container Service',
    'Deep South Sanitation',
    'R-Local Sanitation',
    'Chris Rizzo Trucking',
    'Madras Sanitary Service',
    'Reliable Sanitation',
    'Overton Recycling',
    'Roadrunner Sanitation',
    'Hugill Sanitation',
    'Missoula Compost',
    'Pike County Solid Waste',
    'Larry D Marshall Disposal',
    'Sutton Disposal',
    'Madden Sanitation',
    'Eco Sanitation',
    'Cowboy Sanitation',
    'Ozark Disposal',
    'Capital Area Refuse',
    'Garretson Trash Service',
    'Hotchkiss Disposal',
    'Olson Sanitation',
    'Trinity Disposal',
    'RaeKar',
    'TDS LLC',
    'Thompson Sanitation',
    'Byre Brothers',
    'Ace Sanitation Service',
    'Hudgins Disposal',
    'Disposal Services LLC',
    'Pratt Sanitation',
    'B-N-C Trash Service',
    'Tygarts Valley Sanitation',
    'Big River Disposal',
    'Town & Country Sanitation',
    'T & G Sanitation',
    "Steve's Sanitation",
    'Valley Sanitation LLC',
    'Waterman Recycling',
    'Prestige Disposal',
    'Solid Rock Waste',
    'T-Mac Inc',
    'Allen Disposal',
    'Golden Environmental',
    'Waste Disposal Services',
    'Hart Sanitation',
    "Ava's Waste Removal",
    "Marick's Waste Disposal",
    # V8 Batch 4 - Additional TrashBilling vendors (payment receipts)
    # 'Bliss Environmental',  # V10: Has ACCOUNT NO. - moved to extractors
    'Greenbrier Valley Solid Waste',
    'Butler Disposal Systems',
    "Mike's Rubbish",
    'The Trash Man',
    'Miller Enterprises',
    'Garden State Waste Management',
    'BFI Waste',
    'Klumm Brothers',
    'Wisneski Westmoreland',
    'Roberts Enterprises',
    'Cressman Sanitation',
    'Rapid Removal',
    'Tri-City Disposal',
    'Snake River Rubbish',
    'ABS Sanitation',
    'Mosdell Sanitation',
    'Young Refuse',
    'Pro Disposal',
    'L&L Site Services',
    "Wright's Environmental",
    'Countryside Disposal',
    'Earthwise Waste Solutions',
    'U & I Sanitation',
    'Wingfield Service',
    'A&J Trash',
    'Jackson County Solid Waste',
    'Maverick Waste',
    'The Trash Guys',
    'MDS Waste',
    'Moler Sanitation',
    'Volunteer Disposal West',
    'Coles County Sanitation',
    'Greenway Waste',
    'BNB Disposal',
    'Mountain Disposal Inc',
    "Clark's Disposal",
    'North Georgia Waste',
    'Sutter Disposal',
    'Get Rid Of It Waste',
    'J & S Trash Collection',
    'Edge Waste',
    'Mid-Ohio Sanitation & Recycling',
    'Delta Disposal',
    'Loren Fischer Disposal',
    'Anaconda Disposal',
    'Marcotte Disposal',
    "Martin's Trash Service",
    'Hamilton Recycling Disposal',
    'BCDA The Trash Company',
    'Liberty Ashes',
    'Lakeside Recycling',
    'Harper Sanitation',
    'J & M Sanitation',
    # V8 Batch 5 - Invoice-only vendors (no account number in samples)
    'Pop and Son Trucking',
    'City of Lompoc',
    'Mission Trail Waste',
    'Marion County Fiscal Court',
    'Cook Maintenance',
    'Taylor & Sons',
    'CRP Sanitation',
    "Weaver's Sanitation",
    'Florida Waste Solutions',
    'Akat Scrap Metal',
    "Jim's Sanitation",
    'Pro Waste Services',
    'Empire Recycling Corporation',
    'City of Bakersfield',
    'City of Dickson',
    'Rhino Waste',
    'Kamps Pallets',
    'City of Red Wing',
    'Emery County Sanitation',
    'Heartland Waste Management',
    'WillScot',
    'Royal Document Destruction',
    'Rick Taylor',
    'A&I Pallets',
    'The Shred Truck',
    'Ridgerunner Container',
    'Hometown Sanitation',
    'UDP TN Hauling',
    'Marborg',
    'United Rentals',
    'Bi-County Disposal',
    'Lawrence County Solid Waste',
    'Coastal Environmental Service',
    'Washler Garbage',
    'CWRR',
    'Andy Gump',
    'Allstate Equipment Services',
    'AM Disposal',
    'ADS Solid Waste',
    'CTL Washington',
    'Satellite Shelters',
    'City of Buford',
    'Premier Disposal',
    # 'F & L Construction',  # V10: Has CUSTOMER NO. - moved to extractors
    'Food To Power',
    # 'BP Trucking',  # V10: Has CUSTOMER NO. - moved to extractors
    'Pete and Pete',
    'Mid South Waste',
    'Veolia',
    'Tennis Sanitation',
    'Roller Industrial',
    'City of Tulare',
    'AMG Resources',
    'Mazza Recycling',
    'Kern County Public Works',
    'Junk Removed Now',
    'Shank Waste',
    '3R Technology',
    'Haul Away Waste',
    'City of Columbia MO',
    'Peerless Industries',
    'Big Horn Co-op',
    'Trash Express',
    'Town of Truckee',
    'All American Waste',
    'H & S Enterprises',
    'Wesco',
    'City of Live Oak',
    'City of Turlock',
    'River City Disposal',
    'Schramm Inc',
    'Trash Away',
    'Cascade Disposal',
    'Clean Ohio',
    'City of Saint Augustine',
    'City of Tooele',
    'Trash King',
    'Toter',
    'Landfill Garbage Disposal',
    'Shiloh Recycling',
    'Redmon Inc',
    'North Star',
    'J & J Sanitation Service',
    "Murphy's Sanitation",
    "Charlie's Sanitation",
    'Twin City Refuse',
    'PappaJohn',
    'W M Waste',
    'City of Ozark',
    'City of Valley',
    'Tri-County Waste Management',
    'City of Vidalia',
    'Solid Waste Management',
    'Accu-Sort',
    'Shred Nations',
    'Green Waste Solutions',
    'Jaco Environmental',
    'City of Monterey',
    'Town of Zionsville',
    'City of Saint Cloud',
    'City of Sedalia',
    'Eco-Site',
    'City of Marianna',
    'Heil Environmental',
    'City of Lubbock',
    'City of Pittsburg',
    'General Equipment Rental',
    'Western Waste Industries',
    'Midwest Shredding',
    'Gopher Resource',
    'Certified Shred',
    'Absolute Waste Services',
    'Total Recycling Services',
    'City of Cleburne',
    'City of Conway',
    'City of Murray KY',
    'City of Heber Springs',
    'City of Lawton',
    'Recyclex',
    'A Plus Recycling',
    'Allied Paper Recyclers',
    'Vanguard Compactor',
    'Manheim Sanitation',
    'PennWaste',
    'City of Salina',
    'City of Claremore',
    'City of Russellville',
    'City of El Centro',
    'City of Paragould',
    'City of Bartlesville',
    'City of Fort Smith',
    'City of Dodge City',
    'City of McPherson',
    'City of Clinton',
    'City of Pryor',
    'City of Liberal',
    'City of Muskogee',
    'City of Ada',
    'City of Miami OK',
    'City of Ardmore',
    'City of Duncan',
    'City of Stillwater',
    'City of Ponca City',
    'City of Shawnee',
    'City of Chickasha',
    'City of Altus',
    'City of Weatherford',
    'City of Durant',
    'City of El Reno',
    'City of Guthrie',
    'City of Blackwell',
    'City of Tahlequah',
    'City of Alva',
    'City of Hugo',
    'City of Guymon',
    'City of Woodward',
    'City of Elk City',
    'City of Vinita',
    'City of Atoka',
    'City of Idabel',
    'City of McAlester',
    'City of Poteau',
    'City of Seminole',
    'City of Pauls Valley',
    'City of Sulphur',
    'City of Wewoka',
    'City of Purcell',
    'City of Blanchard',
    'City of Coalgate',
    'City of Antlers',
    'City of Stigler',
    'City of Wilburton',
    'City of Eufaula',
    'City of Heavener',
    'City of Sallisaw',
    'City of Wagoner',
    'City of Prattville',
    'City of Moultrie',
    'City of Valdosta',
    'City of Douglas',
    'City of Waycross',
    'City of Thomasville',
    'City of Americus',
    'City of Tifton',
    'City of Cordele',
    'City of Cairo',
    'City of Bainbridge',
    'City of Camilla',
    'City of Fitzgerald',
    'City of Jesup',
    'City of Vidalia GA',
    'City of Blackshear',
    'City of Hazlehurst',
    'City of Alma',
    'City of Quitman',
    'City of Pelham',
    'City of Adel',
    'City of Nashville GA',
    # V8 Batch 5 continued - More invoice-only vendors
    "Jon's Refuse Solutions",
    'United Waste Haulers',
    'Bainbridge Disposal',
    'CompostNow',
    'C Stoneham',
    'Mills Bros',
    'City of Pleasanton',
    'Tomorrow RDS',
    'Georgetown Paper Stock',
    'Hillsboro Garbage Disposal',
    'Minnkota Recycling',
    'EWE Equipment',
    'Weiner Iron & Metal',
    'CTL 3R Technology',
    'R&R Recycling Inc',
    'Crown Waste & Recycling',
    'Chum Refuse',
    'First Capitol Salvage',
    'P&S Trucking',
    'Dirty Boyz Sanitation',
    'MaxShred',
    'D & D Refuse',
    'SRG Spartanburg',
    'Kept Companies',
    'White Mountain Apache',
    'C & H Disposal',
    'Waste Recycling Inc',
    'Eagle Equipment Corporation',
    'LCI Services',
    'Generated Materials Recovery',
    'Pleasanton Garbage',
    'Main Street Fibers',
    'Kluesner Sanitation',
    'Mauldin Trash',
    'Seagraves Plumbing',
    'American Hauling Services',
    'HESCO Hydraulic',
    'Columbia County Solid Waste',
    'Tate Services',
    'Local Waste of Upstate',
    'Sphuler Disposal',
    'S.B. Cox',
    'TEG Lease',
    'McDowell & Sons Sanitation',
    'Tri-State Carting',
    'Hillsborough County SW',
    'Jazme',
    '501 Sanitation',
    'Far West Recycling',
    'Countrywide Sanitation',
    # V8 Batch 6 - Final batch - vendors with complex columnar formats
    'Debris to Green',
    'C & D Disposal',
    'First Piedmont',
    'Rich County',
    'CWPM',
    'Norland Environmental',
    'Updike Industries',
    'Miami-Dade DSWM',
    'Whitecap Waste',
    'Seadrunar Recycling',
    'Industrial Services Lincoln',
    'Bridge City Sanitation',
    'TFC Recycling',
    'South Tahoe Refuse',
    'City of Pembroke Pines',
    'Pascon',
    'City of Athens GA',
    'TransTrash',
    'Pederson Sanitation',
    'City of Sierra Vista',
    'Major Waste',
    'Vasco Road Landfill',
    'City of Sevierville',
    'City of Hickory',
    'Cedar Grove',
    'Martin Environmental',
    'East Central Kansas',
    'CSD Disposal',
    'Apple Valley Waste',
    'Richardson Waste',
    'City of Sherman',
    'Intermountain Disposal',
    'Ideal Trash and Recycling',
    'Paso Robles Waste',
    'Ontario Municipal',
    "Howie's Trash Service",
    'Coos Bay Sanitary',
    'City of Visalia',
    'City of Boynton Beach',
    'City of Fayette',
    'Cram-A-Lot',
    'Town of Limon',
    'Sonoran Ranch',
    "Ed's Disposal",
    'Town of Lake Park',
    'Penn Waste',
    'Rubatino Refuse',
    'Olcese Waste Services',
    'H-Town Hauling',
    'Dillon Disposal',
    'City of McDonough',
    'Quality Waste',
    'Sunshine Disposal & Recycling',
    'GreenWaste',
    'City of Cookeville',
    'Dugger Trash Service',
    'Equipment Depot Northeast',
    'Brask Enterprises',
    'Circle Sanitation',
    'Blue Moon',
    'D&S Portable Toilets',
    'Weidle Sanitation',
    'Hepaco',
    'Greif',
    'Waste Reduction Sys',
    'BCC Waste Solutions',
    'Document Destruction of Virginia',
    'Uribe Refuse',
    'Iron City Express',
    'City of Great Falls',
    'City of St Anthony',
    'National Waste & Disposal',
    'Southern Disposal AR',
    'Napa Recycling',
    'City of Snellville',
    'City of Temple TX',
    'Choice Waste Services',
    'Marin Sanitary',
    'Complete Solutions & Sourcing',
    'WM Compactor Solutions',
    'Swinger Sanitation',
    'City of Mont Belvieu',
    'Pellitteri',
    'Hale County Public Works',
    'City of Somerset',
    'Alpha Waste Disposal',
    # 'Mills Brothers',  # V10: Has ACCT - moved to extractors
    'American Sanitation',
    'Waste Resources Gardena',
    'Tahoe Truckee Sierra Disposal',
    'Tri-County Industries',
    'Barbarino Disposal',
    'NEI Pennsylvania',
    "Jay Mecham's",
    'K-Town Disposal',
    'Basin Haulage',
    'Bavarian Waste',
    'American Reclamation',
    'MCUD Manatee',
    'City of Wolf Point',
    # V8 Batch 6 continued
    'Lex Serv',
    'Stewart Sanitation',
    'Georgia Waste Systems',
    'RAD Curbside',
    'Lake Disposal Service',
    'City of Ketchikan',
    'City of Blackfoot',
    'American Waste Control',
    'Island Disposal',
    'Oregon City Garbage',
    'Happy Can Disposal',
    'Trash Rangers',
    'City of Rowlett',
    'Save That Stuff',
    'City of Conyers',
    'Cloquet Sanitary',
    'Quincy Recycling',
    'Russell County Sanitation',
    'Nisswa Sanitation',
    'Gardner Disposal Service',
    # "Good's Disposal",  # V10: Has CUSTOMER NO. - moved to extractors
    'Southeast Waste Disposal',
    'Gmen Environmental',
    'PRIDE Disposal',
    'Tropical Trash',
    "Charlie's Waste",
    'City of Sidney',
    'IV Waste',
    'United States Disposal',
    'City of Lewiston',
    'McCullough Rubbish',
    'Kalamazoo Transfer Station',
    'Kootenai County Solid Waste',
    'City of Culver City',
    'Suburban Waste Services',
    'Black Earth Compost',
    'A&C Waste Collection',
    'City of Tulsa',
    'City of Tracy',
    'Agri-Cycle',
    'Serv-Wel Disposal',
    'Douglas Disposal',
    'City of Rockhill',
    'Apex Recycling & Disposal',
    'Friends Garbage',
    'Innovative Trash Service',
    'J&Jay Services',
    'City of Windcrest',
    'Valley Waste Service',
    'BGL Suburban Garbage',
    "Brandt's Sanitary",
    'Real Waste Solutions',
    'Richland County Landfill',
    'Waste Masters',
    'Pacific Sanitation Co',
    'Troupe Waste',
    'Full Circle Recycling',
    'Okon Recycling',
    'City of Las Cruces',
    'Pinto Service',
    "Fogle's",
    'Two Men and a Junk Truck',
    'NS Disposal',
    'Solid Waste Services WV',
    'Marck Recycling and Waste',
    'City of Hidalgo',
    'A&W Iron Metal',
    'HMP Inc',
    'City of Deerfield Beach',
    'Container Rental Co',
    'Texas Dumpsters',
    'Elite Recycling',
    'Great Waste',
    'Smurfit',
    'Pak Rite Rentals',
    "Woodward's Disposal",
    'Dyersburg Gas & Water',
    'Efficient Roll-Off & Recycling',
    'Lusk Disposal',
    'G2 Revolution',
    'Tovar Equipment',
    'Lakeland Disposal WI',
    'City of Huron',
    'Chesapeake Waste',
    'City of Dumas',
    'Reliable Paper',
    'Brandon Industrial Parts',
    'Skyhook',
    'City of Fort Myers',
    'City of Douglasville',
    'Kopchos Sanitation',
    'Lift Waste',
    'Vanderpoel Disposal',
    'Mackenzie Disposal',
    'R & R Midwest',
    'Cumberland Services',
    # 'Total Disposal Inc',  # V10: Has CUSTOMER NO. - moved to extractors
    "Hartel's",
    "Hogland's Transfer",
    'Gogebic Range SWMA',
    # V8 Batch 6 final
    # 'KC Disposal',  # V10: Has ACCT - moved to extractors
    "Abe's Trash Service",
    'Escondido Disposal',
    'Lake Area Disposal',
    'Town of Apple Valley',
    "Sid's Garbage",
    'Reno Forklift',
    'Ramona Disposal',
    'Willey Disposal',
    'Nooksack Valley Disposal',
    'Sanitary Service Company',
    'Hiltz',
    'Panola County Solid Waste',
    'Joseph J. Runner',
    'City of Willcox',
    'Bozzuto BRS Services',
    'Ingrum Waste Disposal',
    'City of Winters',
    'Golden Triangle Waste',
    'Anchor Technical',
    'Tri-State Disposal',
    'Checksammy',
    'Pullman Disposal',
    'Watertown Iron',
    'Junk King',
    'Westport Funding',
    'City of Quincy',
    'Top Dog Waste',
    'Tom Danley Disposal',
    "Dayne's Waste Disposal",
    'Triple H Enterprises',
    'WB Waste Solutions',
    'Kirby Sanitation',
    'Winston Sanitary',
    'Copper State Sanitation',
    "Gil's Sanitation",
    'Top of the Line Dumpsters',
    'All State Waste Inc',
    'City of Nampa',
    'Nevada Recycling',
    'Citrus County Utilities',
    'Salt River Pima',
    'Windsor Sanitation',
    'EZ Disposal',
    'Rockwood Sustainable Solutions',
    'Al Clawson Disposal',
    'Pendleton Sanitary Service',
    "Tim's Trash Service",
    'Horn Sanitation',
    'United Waste Systems',
    'Cogent Waste Solutions',
    'Patterson Sanitation',
    'Control Waste',
    'Green Environmental Services',
    'Humpty Dumpsters',
    'Step Up Disposals',
    'City of Madisonville',
    'Tri County Disposal',
    'Delta Garbage Service',
    'North Port Solid Waste',
    'Recycling Center Inc',
    'Bozeman MT Utilities',
    'City of Craig',
    'Roseburg Disposal',
    'City of Colby',
    'Waste Removal & Recycling',
    'Westside Disposal',
    'City of Dickinson',
    'Palm Springs Disposal',
    'Tacoma Public Utilities',
    'Commonwealth Waste Solutions',
    'Canusa Hershman',
    'Forever Clean',
    'Durflinger Disposal Service',
    'Reliable Paper Recycling',
    'Aspen Leasing',
    'Darling Ingredients',
    'City of Laramie',
    'Jamaica Ash & Rubbish',
    'Capital City',
    'City of Rolla',
    'City of Williston',
    'Dallas Recycling',
    'Nicholas Sanitation',
    'Brannon Industrial',
    'Perdue Environmental',
    'CWSI',
    'Maui Disposal Co',
    'Wasteless Solutions',
    'Hometown Disposal',
    'Centre Water Works',
    'Nisly Brothers',
    'J&R Sanitation',
    'Niese Hauling',
    "Matt's Sanitation",
    'Redwood Landfill',
    'BKI Recycling',
    'City of Scottsbluff',
    'Boston Baler',
    'DC Metals',
    'City of Kirkland',
    'Baker Sanitary Service',
    'DuMontelle Waste',
    'Emterra Environmental',
    'Hughes & Sons',
    'JD Parker',
    'Pluffmud Recycling',
    'Yreka Transfer',
    'Town of Lusk',
    'Ed Burris Disposal',
    'CDA Garbage',
    'Monterey City Disposal',
    'Break It Down',
    'City of Gainesville TX',
    'Breezy Hollow',
    'Alameda County Industries',
    "Dodd's Trash Hauling",
    'Boulder City Disposal',
    'AJ Waste Systems',
    'City of Largo',
    'WM Collection',
    'American Metal & Paper',
    'All Star Roll-Off',
    'City of Richardson',
    'Advanced Document Solutions',
    'City of Hobbs',
    'City of Yuma',
    'City of Devils Lake',
    'City of Tullahoma',
    'City of Loganville',
    "Loren's Sanitation",
    'Town of Greeneville',
    'BestTrash',
    'City of Enumclaw',
    "Adam's Disposal",
    'City of Barstow',
    'Golden Eagle Services',
    'Johnson City Utility',
    'Excess Disposal',
    'City of Socorro',
    'Rahn Sanitary',
    'Kaibab Band',
    'Town of Wickenburg',
    'Town of Dutch John',
    'Big Bear Disposal',
    'City of Lake Mary',
    'City of Del Rio',
    'Desert Valley Disposal',
    'Solid Waste Disposal Authority',
    'Buldo Container & Disposal',
    'City of Lamar',
    'Redfish Recycling',
    'Blue Compactor',
    'Mercer Group',
    'Total Waste Management',
    "Ken's Sanitation",
    'Long Island Waste',
    'Upper Valley Disposal',
    'City of Green River',
]

for vendor in NO_ACCOUNT_VENDORS:
    VENDOR_ACCOUNTS[vendor] = {
        'has_account': False,
        'format': None,
        'examples': [],
        'extract': lambda x: None,
        'notes': 'Invoice-based identification only'
    }


# ============================================================
# VENDOR ADDITIONS (January 2026) - Import and merge
# ============================================================
try:
    from .account_extraction_additions_jan2026 import VENDOR_ADDITIONS
    VENDOR_ACCOUNTS.update(VENDOR_ADDITIONS)
except ImportError:
    try:
        from account_extraction_additions_jan2026 import VENDOR_ADDITIONS
        VENDOR_ACCOUNTS.update(VENDOR_ADDITIONS)
    except ImportError:
        pass


# ============================================================
# VENDOR ADDITIONS (February 2026) - NG Report vendors
# ============================================================
try:
    from .account_extraction_additions_feb2026 import VENDOR_ADDITIONS_FEB2026
    VENDOR_ACCOUNTS.update(VENDOR_ADDITIONS_FEB2026)
except ImportError:
    try:
        # Standalone import (no package context)
        from account_extraction_additions_feb2026 import VENDOR_ADDITIONS_FEB2026
        VENDOR_ACCOUNTS.update(VENDOR_ADDITIONS_FEB2026)
    except ImportError:
        pass


# ============================================================
# VENDOR ADDITIONS (March 2026) - ops_database invoice processing
# ============================================================
try:
    from .account_extraction_additions_mar2026 import VENDOR_ADDITIONS_MAR2026
    VENDOR_ACCOUNTS.update(VENDOR_ADDITIONS_MAR2026)
except ImportError:
    try:
        from account_extraction_additions_mar2026 import VENDOR_ADDITIONS_MAR2026
        VENDOR_ACCOUNTS.update(VENDOR_ADDITIONS_MAR2026)
    except ImportError:
        pass

# ============================================================
# VENDOR ADDITIONS (March 2026 v9.3d) - full corpus patterns
# Only add NEW vendors + explicit overrides for vendors with
# debugged improvements. Never override working base patterns
# with generic label extractors.
# ============================================================
def _make_combined_extractor(base_fn, fallback_fn):
    """Create combined extractor: try base first, fall back to v93d."""
    def combined(text):
        result = base_fn(text)
        if result:
            return result
        return fallback_fn(text)
    return combined

try:
    from .account_extraction_additions_mar2026_v93d import (
        VENDOR_ADDITIONS_MAR2026_V93D, V93D_EXPLICIT_OVERRIDES)
    for k, v in VENDOR_ADDITIONS_MAR2026_V93D.items():
        if k not in VENDOR_ACCOUNTS or k in V93D_EXPLICIT_OVERRIDES:
            # New vendor or explicit override — use v93d entry directly
            VENDOR_ACCOUNTS[k] = v
        elif v.get('has_account') and VENDOR_ACCOUNTS[k].get('has_account'):
            # Vendor exists in base with has_account=True and v93d also has
            # has_account=True — add v93d extractor as fallback
            base_entry = VENDOR_ACCOUNTS[k]
            VENDOR_ACCOUNTS[k] = dict(base_entry)
            VENDOR_ACCOUNTS[k]['extract'] = _make_combined_extractor(
                base_entry['extract'], v['extract'])
except ImportError:
    try:
        from account_extraction_additions_mar2026_v93d import (
            VENDOR_ADDITIONS_MAR2026_V93D, V93D_EXPLICIT_OVERRIDES)
        for k, v in VENDOR_ADDITIONS_MAR2026_V93D.items():
            if k not in VENDOR_ACCOUNTS or k in V93D_EXPLICIT_OVERRIDES:
                VENDOR_ACCOUNTS[k] = v
            elif v.get('has_account') and VENDOR_ACCOUNTS[k].get('has_account'):
                base_entry = VENDOR_ACCOUNTS[k]
                VENDOR_ACCOUNTS[k] = dict(base_entry)
                VENDOR_ACCOUNTS[k]['extract'] = _make_combined_extractor(
                    base_entry['extract'], v['extract'])
    except ImportError:
        pass


# ============================================================
# PUBLIC API
# ============================================================

def extract_account(vendor_name: str, text: str) -> Optional[str]:
    """
    Extract account number from invoice text for a given vendor.

    DETERMINISTIC: Returns exact match or None. No guessing.

    Args:
        vendor_name: The detected vendor name (from vendor_detection_module)
        text: The raw OCR text from the invoice

    Returns:
        str or None - The extracted account number, or None if not found/not applicable
    """
    if vendor_name not in VENDOR_ACCOUNTS:
        return None

    config = VENDOR_ACCOUNTS[vendor_name]
    if not config['has_account']:
        return None

    return config['extract'](text)


def get_account_format(vendor_name: str) -> Optional[Dict[str, Any]]:
    """
    Get the account number format description for a vendor.
    
    Returns:
        dict with keys: has_account, format, examples
        or None if vendor not configured
    """
    if vendor_name not in VENDOR_ACCOUNTS:
        return None
    
    config = VENDOR_ACCOUNTS[vendor_name]
    return {
        'has_account': config['has_account'],
        'format': config['format'],
        'examples': config['examples']
    }


def get_configured_vendors() -> List[str]:
    """Return list of all vendors with account extraction configured."""
    return list(VENDOR_ACCOUNTS.keys())


def get_vendor_stats() -> Dict[str, int]:
    """Return summary statistics of configured vendors."""
    total = len(VENDOR_ACCOUNTS)
    with_accounts = sum(1 for v in VENDOR_ACCOUNTS.values() if v['has_account'])
    return {
        'total_configured': total,
        'with_accounts': with_accounts,
        'without_accounts': total - with_accounts
    }


def validate_account_format(vendor_name: str, account: str) -> bool:
    """
    Validate that an account number matches the expected format for a vendor.
    
    Args:
        vendor_name: The vendor name
        account: The account number to validate
        
    Returns:
        bool - True if valid format, False otherwise
    """
    if vendor_name not in VENDOR_ACCOUNTS:
        return False
    
    # Re-extract using the vendor's extraction function
    # If it would extract the same value from text containing it, format is valid
    config = VENDOR_ACCOUNTS[vendor_name]
    if not config['has_account']:
        return False
    
    # Simple validation - check if account matches example patterns
    examples = config.get('examples', [])
    if not examples:
        return True  # No examples to validate against
    
    # Check if account has similar structure to examples
    example = examples[0]
    if len(account) < len(example) - 2 or len(account) > len(example) + 2:
        return False
    
    return True


# ============================================================
# MAIN - Testing and Validation
# ============================================================

if __name__ == '__main__':
    print("Account Extraction Engine v2.0")
    print("=" * 70)
    
    stats = get_vendor_stats()
    print(f"Total configured vendors: {stats['total_configured']}")
    print(f"  - With account numbers: {stats['with_accounts']}")
    print(f"  - Without account numbers: {stats['without_accounts']}")
    
    print("\n" + "=" * 70)
    print("VENDOR ACCOUNT FORMATS (Alphabetical)")
    print("=" * 70)
    
    for vendor, config in sorted(VENDOR_ACCOUNTS.items()):
        if config['has_account']:
            examples = config['examples'][:2]
            print(f"\n{vendor}")
            print(f"  Format: {config['format']}")
            print(f"  Examples: {examples}")
        else:
            print(f"\n{vendor}")
            print(f"  No account number - invoice-based identification")
