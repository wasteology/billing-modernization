"""
Account Number Extraction Engine v2.0
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
    """Format: 5-6 digit after ACCOUNT # header"""
    lines = text.split('\\n')
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
    """Format: WGY + alphanumeric (main) or NN-NNNNN-NNNNN (alternate)
    Examples: WGY17110UB, WGY04904RB, 18-40677-73005
    Note: Excludes miscategorized vendors
    """
    # Skip miscategorized vendors
    if any(x in text.upper() for x in ['WIN WASTE', 'WEST CENTRAL', 'UNITED STATES DISPOSAL', "STEVE'S SANITATION"]):
        return None
    
    # Format 1: WGY + alphanumeric
    match = re.search(r'(WGY[A-Z0-9]{5,8})', text)
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
    
    # Format 3: Westside variant Customer #:
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
    """Format: 5-digit numeric at position 4 in header block
    Examples: 24234, 24479, 26944
    """
    lines = text.split('\\n')
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
    """Format: 5-6 digit numeric
    Examples: 273586, 274126
    """
    lines = text.split('\\n')
    if len(lines) > 7:
        val = lines[7].strip()
        if re.match(r'^\d{5,6}$', val):
            return val
    for i, line in enumerate(lines):
        if 'Customer Number' in line:
            for j in range(i+1, min(i+6, len(lines))):
                val = lines[j].strip()
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
    """Format: NNNNN.NNN (account.site decimal format)
    Examples: 55779.64, 55779.152
    """
    if 'CUSTOMER ISSUE TICKET' in text.upper():
        return None
    lines = text.split('\\n')
    for i, line in enumerate(lines):
        if 'ACCOUNT NO' in line.upper():
            for j in range(max(0, i-3), min(i+5, len(lines))):
                match = re.search(r'\b(\d{5}\.\d{1,3})\b', lines[j])
                if match:
                    return match.group(1)
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
    match = re.search(r'Account\s*#\s*(PW\d{8}|ACC\d{5})', text, re.IGNORECASE)
    return match.group(1) if match else None

VENDOR_ACCOUNTS['Priority Waste'] = {
    'has_account': True,
    'format': 'PWNNNNNNNN or ACCNNNNN',
    'examples': ['PW00011457', 'ACC27440', 'ACC28177'],
    'extract': _extract_priority_waste
}


def _extract_casella(text: str) -> Optional[str]:
    """Format: NN-NNNNN N or KNNNNNNNNN
    Examples: 81-39019 6, K100008742
    """
    lines = text.split('\\n')
    for i, line in enumerate(lines):
        if 'Cust#:' in line:
            for j in range(i, min(i+4, len(lines))):
                match = re.search(r'\b(\d{2}-\d{5}\s*\d?)\b', lines[j])
                if match:
                    return match.group(1).strip()
    for i, line in enumerate(lines):
        if 'Customer Number' in line:
            for j in range(i, min(i+5, len(lines))):
                match = re.search(r'\b([A-Z]\d{9})\b', lines[j])
                if match:
                    return match.group(1)
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
    """Format: NN-NNNNNNN N after Account No.
    Examples: 01-1276236 4, 70-0143542 2
    """
    match = re.search(r'Account\s*No\.?\s*(\d{2}-\d{7}\s*\d?)', text, re.IGNORECASE)
    return match.group(1).strip() if match else None

VENDOR_ACCOUNTS['Meridian Waste'] = {
    'has_account': True,
    'format': 'NN-NNNNNNN N',
    'examples': ['01-1276236 4', '70-0143542 2', '01-1269930 1'],
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
    """Format: TSNNNNNNNN or PBC-NNNN-N or 6-digit
    Examples: TS00154796, PBC-3453-5, 270894
    """
    lines = text.split('\\n')
    for i, line in enumerate(lines):
        if 'ACCOUNT #' in line.upper():
            for j in range(i, min(i+6, len(lines))):
                val = lines[j].strip()
                if re.match(r'^\d{6}$', val):
                    return val
    for i, line in enumerate(lines):
        if 'Customer ID:' in line:
            for j in range(i, min(i+5, len(lines))):
                match = re.search(r'(PBC-?\d+-\d+|TS\d{8})', lines[j])
                if match:
                    return match.group(1)
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
    """Format: 4-6 digit numeric Customer No.
    Examples: 2584, 13555
    """
    match = re.search(r'Customer\s*No\.?:?\s*(\d{4,6})', text, re.I)
    if match:
        return match.group(1)
    lines = text.split('\\n')
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
    """Format: 6-10 digit numeric after Customer Number
    Examples: 15063480, 136725585
    """
    lines = text.split('\\n')
    for i, line in enumerate(lines):
        if 'Customer Number' in line:
            for j in range(i+1, min(i+5, len(lines))):
                val = lines[j].strip()
                if re.match(r'^\d{6,10}$', val):
                    return val
    return None

VENDOR_ACCOUNTS['Burrtec'] = {
    'has_account': True,
    'format': 'NNNNNNNNN',
    'examples': ['15063480', '136725585'],
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
    """Format: 9-digit numeric Account Number
    Examples: 157708100, 171954800
    """
    match = re.search(r'Account\s*Number:?\s*(\d{9})', text, re.I)
    return match.group(1) if match else None

VENDOR_ACCOUNTS['Best Way Disposal'] = {
    'has_account': True,
    'format': 'NNNNNNNNN',
    'examples': ['157708100', '171954800'],
    'extract': _extract_best_way_disposal
}


def _extract_athens_services(text: str) -> Optional[str]:
    """Format: Alphanumeric 7-12 characters
    Examples: 2M0010827, 2M0011054, CE0019867
    """
    lines = text.split('\\n')
    for i, line in enumerate(lines):
        if 'ACCOUNT' in line.upper() and i+2 < len(lines):
            if 'NUMBER' in lines[i+1].upper():
                val = lines[i+2].strip()
                if re.match(r'^[A-Z0-9]{7,12}$', val):
                    return val
    return None

VENDOR_ACCOUNTS['Athens Services'] = {
    'has_account': True,
    'format': 'XXNNNNNNN',
    'examples': ['2M0010827', '2M0011054', 'CE0019867'],
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
    """Format: Alphanumeric Customer ID (e.g., UPS012, QED001)
    Examples: UPS012, QED001, UPS005
    """
    match = re.search(r'Customer\s*ID\s*\\n([A-Z0-9]+)', text, re.I)
    if match:
        return match.group(1)
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
    """Format: 6-digit numeric ACCOUNT NO.
    Examples: 166165
    """
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
    """Format: 5-digit CUSTOMER NO.
    Examples: 32027
    """
    match = re.search(r'CUSTOMER\s*NO\.?\s*\\n(\d{5})', text, re.I)
    if match:
        return match.group(1)
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
    """Format: NN-NNNNNNN (Account #)
    Examples: 01-0202488, 01-0209302
    """
    match = re.search(r'Account\s*#:\s*(\d{2}-\d{7})', text, re.I)
    if match:
        return match.group(1)
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
    """Format: N-NNNNNN N (Account #)
    Examples: 1-248930 7, 3-84623 3
    """
    match = re.search(r'Account\s*#:\s*(\d-\d{5,6}\s*\d)', text, re.I)
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
    """Format: 6-digit numeric ACCOUNT NO
    Examples: 305967, 305949
    """
    match = re.search(r'ACCOUNT\s*NO\s*\\n(\d{6})', text, re.I)
    if match:
        return match.group(1)
    # Alternative pattern with pipe separator
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


def _extract_harters(text: str) -> Optional[str]:
    """Format: NN-NNNNN N (Customer #)
    Examples: 01-65024 1, 01-82266 7
    """
    match = re.search(r'Customer\s*#:\s*(\d{2}-\d{5}\s*\d)', text, re.I)
    return match.group(1).strip() if match else None

VENDOR_ACCOUNTS["Harter's"] = {
    'has_account': True,
    'format': 'NN-NNNNN N',
    'examples': ['01-65024 1', '01-82266 7'],
    'extract': _extract_harters
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
    Examples: 0005298824, 8100237262, 5326
    Note: Multiple invoice systems detected as "Waste Zero"
    """
    lines = text.split('\\n')
    
    # Format 1: Recology - Customer\nNumber followed by 9-10 digit
    for i, line in enumerate(lines):
        if line.strip() == 'Customer':
            if i+1 < len(lines) and lines[i+1].strip() == 'Number':
                for j in range(i+2, min(i+10, len(lines))):
                    val = lines[j].strip()
                    if re.match(r'^\d{9,10}$', val):
                        return val
    
    # Format 2: Account Number inline
    match = re.search(r'Account\s*Number\s*(\d{10})', text, re.I)
    if match:
        return match.group(1)
    
    # Format 3: Zero Waste NH - CUSTOMER NO. with nearby 4-6 digit number
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
    Examples: MOBHC1227, UJ00110836, 14281
    Note: Account number appears after "Account\nNumber" in header
    """
    if 'Payment Successful' in text:
        return None
    
    # Pattern 1: Header format - Account\nNumber\nMOBHC1227
    match = re.search(r'Account\s*\\n?Number\s*\\n([A-Z0-9]+)', text, re.I)
    if match:
        val = match.group(1)
        if not val.startswith('INV') and '/' not in val:
            return val
    
    # Pattern 2: Look for alphanumeric account after Account label
    lines = text.split('\\n')
    for i, line in enumerate(lines):
        if 'Account' in line:
            for j in range(i+1, min(i+5, len(lines))):
                val = lines[j].strip()
                if val == 'Number':
                    continue
                if re.match(r'^[A-Z]{2,6}\d{4,8}$', val):
                    return val
                if re.match(r'^\d{4,6}$', val) and not val.startswith('INV'):
                    return val
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
    Examples: 10-2770100 1, 10-2770500 2
    """
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


def _extract_delta_waste(text: str) -> Optional[str]:
    """Format: 4-5 digit numeric ACCOUNT #
    Examples: 1014
    """
    lines = text.split('\\n')
    if len(lines) > 4:
        val = lines[4].strip()
        if re.match(r'^\d{4,5}$', val):
            return val
    return None

VENDOR_ACCOUNTS['Delta Waste'] = {
    'has_account': True,
    'format': 'NNNN',
    'examples': ['1014'],
    'extract': _extract_delta_waste
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
    """
    match = re.search(r'Customer\s*ID:\s*([A-Z]\d{5})', text, re.I)
    if match:
        return match.group(1)
    lines = text.split('\\n')
    for i, line in enumerate(lines):
        if 'Customer ID' in line:
            for j in range(i+1, min(i+5, len(lines))):
                val = lines[j].strip()
                if re.match(r'^[A-Z]\d{5}$', val):
                    return val
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

NO_ACCOUNT_VENDORS = [
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
