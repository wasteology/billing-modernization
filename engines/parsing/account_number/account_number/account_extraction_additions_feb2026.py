"""
Account Extraction Additions - February 2026
Patterns for NG Report invoice processing pipeline.

42 vendors identified from Waste Harmonics invoice folder.
"""
import re
from typing import Optional


# ============================================================
# EXTRACTION FUNCTIONS
# ============================================================

def _extract_zero_waste(text: str) -> Optional[str]:
    """Format: Account: NNNNN or Project No: NNNNN.NNN
    Example: Account: 24600, Project No: 24600.000
    """
    match = re.search(r'Account:\s*(\d{4,6})', text)
    if match:
        return match.group(1)
    match = re.search(r'Project No:\s*(\d{4,6})', text)
    if match:
        return match.group(1)
    return None


def _extract_national_waste_services(text: str) -> Optional[str]:
    """Format: Date | NNNNNNNX or Date NNNNNNNX (alphanumeric after date)
    Examples: 10/1/2025 | 1815350A, 8/1/2025 18067454
    """
    # Format 1: With pipe
    match = re.search(r'\d{1,2}/\d{1,2}/\d{4}\s*\|\s*(\d{6,8}[A-Z]?)', text)
    if match:
        return match.group(1)
    # Format 2: Without pipe (space separated)
    match = re.search(r'\d{1,2}/\d{1,2}/\d{4}\s+(\d{7,8}[A-Z]?)\b', text)
    if match:
        return match.group(1)
    return None


def _extract_town_of_gilbert(text: str) -> Optional[str]:
    """Format: Customer Account Number NNNNNNNN-NNNNNN
    Example: 00555500-105245
    """
    match = re.search(r'Customer Account Number\s*(\d{8}-\d{6})', text, re.I)
    if match:
        return match.group(1)
    match = re.search(r'Account Number\s*(\d{8}-\d{6})', text, re.I)
    if match:
        return match.group(1)
    return None


def _extract_city_of_oxnard(text: str) -> Optional[str]:
    """Format: ACCOUNT NUMBER ... NNNNNN-NNNNNN or standalone
    Example: 312315-304035
    FIX: Also match standalone NNNNNN-NNNNNN when near Oxnard text.
    """
    match = re.search(r'ACCOUNT NUMBER.*?(\d{6}-\d{6})', text, re.I | re.S)
    if match:
        return match.group(1)
    # Standalone format
    match = re.search(r'\b(\d{6}-\d{6})\b', text)
    if match:
        return match.group(1)
    return None


def _extract_sbc_waste(text: str) -> Optional[str]:
    """Format: Account Number NN-NNNNNNN N (with optional check digit)
    Examples: 10-3323705, 10-3314190 3, 10-10934 7
    FIX: Handle multi-line OCR where label and value are on separate lines.
    Also handle shorter account numbers (NN-NNNNN).
    """
    normalized = text.replace('\\n', '\n')

    # Format 1: Inline - Account Number NN-NNNN(NNN) (4-7 digits after dash)
    match = re.search(r'Account Number\s*(\d{2}-\d{4,7})\s*\d?', normalized, re.I)
    if match:
        return match.group(1)

    # Format 2: Multi-line - Account Number on one line, value on next
    lines = normalized.split('\n')
    for i, line in enumerate(lines):
        if 'Account Number' in line:
            for j in range(i + 1, min(i + 8, len(lines))):
                val = lines[j].strip()
                m = re.match(r'^(\d{2}-\d{4,7})\s*\d?$', val)
                if m:
                    return m.group(1)
    return None


def _extract_waste_disposal_az(text: str) -> Optional[str]:
    """Format: Customer Number: NNNNNNN
    Example: 1787887
    """
    match = re.search(r'Customer Number:\s*(\d{6,8})', text, re.I)
    if match:
        return match.group(1)
    return None


def _extract_lepage_sons(text: str) -> Optional[str]:
    """Format: Customer Number NN-NNNNN N
    Example: 01-11303 0
    Also: Local Waste Solutions header
    """
    match = re.search(r'Customer Number\s*(\d{2}-\d{5}\s*\d?)', text, re.I)
    if match:
        return match.group(1).strip()
    return None


def _extract_tate_services(text: str) -> Optional[str]:
    """Format: CUSTOMER NO NNNNNN
    Example: 010245
    """
    match = re.search(r'CUSTOMER NO\s*(\d{5,7})', text, re.I)
    if match:
        return match.group(1)
    return None


def _extract_kmg_hauling(text: str) -> Optional[str]:
    """Format: CUSTOMER NO NNNNNN
    Examples: 006238, 005523, 005513
    FIX: Handle multi-line OCR where label and value are on separate lines.
    OCR typically shows: CUSTOMER NO\\n005523
    """
    normalized = text.replace('\\n', '\n')

    # Format 1: Inline - CUSTOMER NO 005523
    match = re.search(r'CUSTOMER NO\.?\s*(\d{5,7})', normalized, re.I)
    if match:
        return match.group(1)

    # Format 2: Multi-line - CUSTOMER NO on one line, value on next
    lines = normalized.split('\n')
    for i, line in enumerate(lines):
        if 'CUSTOMER NO' in line.upper():
            for j in range(i + 1, min(i + 4, len(lines))):
                val = lines[j].strip()
                if re.match(r'^\d{5,8}$', val):
                    return val
    return None


def _extract_waste_pro(text: str) -> Optional[str]:
    """Format: Account Number: NNNNNN
    Example: 231549
    """
    match = re.search(r'Account Number:\s*(\d{5,7})', text, re.I)
    if match:
        return match.group(1)
    return None


def _extract_earthwise_waste(text: str) -> Optional[str]:
    """Format: ID# NNNNNNNNNNNN (12 digit)
    Example: 127300001759
    Also uses TrashBilling
    """
    match = re.search(r'ID#\s*(\d{10,12})', text)
    if match:
        return match.group(1)
    return None


def _extract_modern_recycling(text: str) -> Optional[str]:
    """Format: Customer Number: NNNN or Service Number: NNNNNN - NNNN
    Example: 4179
    """
    match = re.search(r'Customer Number:\s*(\d{4,6})', text, re.I)
    if match:
        return match.group(1)
    match = re.search(r'Service Number:\s*(\d{6})\s*-\s*(\d{4})', text, re.I)
    if match:
        return match.group(2)  # Return customer portion
    return None


def _extract_check_sammy(text: str) -> Optional[str]:
    """Format: Account No. XXNNNNN (alphanumeric)
    Example: WH17455
    """
    match = re.search(r'Account No\.\s*([A-Z]{2}\d{5})', text, re.I)
    if match:
        return match.group(1)
    return None


def _extract_marborg(text: str) -> Optional[str]:
    """Format: Customer Number with spaces N -NNNNNN N
    Example: 6 -110313 6 or 6 -111598 1
    """
    # Format 1: Customer Number label
    match = re.search(r'Customer Number[:\s]*(\d\s*-\d{6}\s*\d)', text, re.I)
    if match:
        return match.group(1).replace(' ', '')
    # Format 2: Account format with spaces (standalone)
    match = re.search(r'(\d\s+-\d{6}\s+\d)', text)
    if match:
        return match.group(1).replace(' ', '')
    # Format 3: No spaces
    match = re.search(r'(\d-\d{6}-?\d)', text)
    if match:
        return match.group(1).replace('-', '', 1) if match.group(1).count('-') > 1 else match.group(1)
    return None


def _extract_edco_disposal(text: str) -> Optional[str]:
    """Format: NN-XX NNNNNN (with letters)
    Example: 59-AN 354951
    """
    match = re.search(r'(\d{2}-[A-Z]{2}\s*\d{6})', text)
    if match:
        return match.group(1).replace(' ', '')
    return None


def _extract_container_rentals(text: str) -> Optional[str]:
    """Format: Work Order # NNNNNN
    Example: 133701
    Note: No customer account, uses work order
    """
    match = re.search(r'Work Order\s*#\s*(\d{5,7})', text, re.I)
    if match:
        return match.group(1)
    return None


def _extract_meridian_waste(text: str) -> Optional[str]:
    """Format: Account No. = NN-NNNNNNN N
    Example: 11-1193076 3
    """
    match = re.search(r'Account No\.\s*=?\s*(\d{2}-\d{7}\s*\d?)', text, re.I)
    if match:
        return match.group(1).strip()
    return None


def _extract_athens_services(text: str) -> Optional[str]:
    """Format: Multiple formats - alphanumeric codes
    Examples: CV0011558, 1M0011195, GM-89, ES-744, ATH1201C
    FIX: Restore multi-line ACCOUNT\\nNUMBER\\nvalue handling that was in the
    base engine. OCR shows: ACCOUNT\\nNUMBER\\nCV0011558
    """
    normalized = text.replace('\\n', '\n')

    # Format 0: ACCOUNT XX-NNN ACCESS (NG invoice format)
    match = re.search(r'ACCOUNT\s+([A-Z]{2}-\d{2,5})\s+ACCESS', normalized, re.I)
    if match:
        return match.group(1)

    # Format 1: Multi-line ACCOUNT / NUMBER / value
    lines = normalized.split('\n')
    for i, line in enumerate(lines):
        if 'ACCOUNT' in line.upper():
            for j in range(i, min(i + 5, len(lines))):
                if 'NUMBER' in lines[j].upper() or j > i:
                    for k in range(j, min(j + 4, len(lines))):
                        val = lines[k].strip()
                        # Match alphanumeric: XX0010827, 1M0011195, CV0011558
                        if re.match(r'^[A-Z0-9]{2}\d{7}$', val):
                            return val
                        # Match XX-NNNN(N): LB-2330, CE-19867, 2M-8028, DW-30844
                        if re.match(r'^[A-Z0-9]{2}-\d{3,5}$', val):
                            return val

    # Format 2: ** SUB ACCT: XX-NN
    match = re.search(r'SUB ACCT:\s*([A-Z]{2}-\s*\d{2,5})', normalized, re.I)
    if match:
        return match.group(1).replace(' ', '')

    # Format 3: ATH + digits + optional letter (e.g. ATH1201C)
    match = re.search(r'\b(ATH\d{3,6}[A-Z]?)\b', normalized)
    if match:
        return match.group(1)

    return None


def _extract_aspen_waste(text: str) -> Optional[str]:
    """Format: Account No. N -NNNNN N (with spaces) or standalone
    Example: 1 -51646 5
    FIX: Also match without label when near ASPEN WASTE text.
    """
    match = re.search(r'Account No\.\s*(\d\s*-\d{5}\s*\d)', text, re.I)
    if match:
        return match.group(1).replace(' ', '')
    match = re.search(r'Acct\.?\s*No\.?\s*(\d\s*-\d{5}\s*\d)', text, re.I)
    if match:
        return match.group(1).replace(' ', '')
    # Standalone format near ASPEN WASTE header
    if 'ASPEN WASTE' in text.upper():
        match = re.search(r'\b(\d\s*-\d{5}\s*\d)\b', text)
        if match:
            return match.group(1).replace(' ', '')
    return None


def _extract_modern_disposal(text: str) -> Optional[str]:
    """Format: Customer Number: NNNN (same as Modern Recycling)
    Example: 4179
    """
    return _extract_modern_recycling(text)


def _extract_veit(text: str) -> Optional[str]:
    """Format: CUSTOMER NO. NNNNN
    Example: 10735
    """
    match = re.search(r'CUSTOMER NO\.\s*(\d{4,6})', text, re.I)
    if match:
        return match.group(1)
    return None


def _extract_usa_waste(text: str) -> Optional[str]:
    """Format: ACCOUNT # NNNNNN (6 digit)
    Examples: 004862
    Also: Customer ID: N-NNNNN-NNNNN (WM format)
    """
    # Format 1: ACCOUNT # NNNNNN
    match = re.search(r'ACCOUNT\s*#\s*(\d{5,7})', text, re.I)
    if match:
        return match.group(1)
    # Format 2: Customer ID (WM format)
    match = re.search(r'Customer ID:\s*(\d-\d{5}-\d{5})', text, re.I)
    if match:
        return match.group(1)
    return None


def _extract_county_hauling(text: str) -> Optional[str]:
    """Format: WM format - VENDOR ACCOUNT NUMBER NNA-NNNNN or NNANNNNN
    Example: 70A-17595, 70A17595
    Note: This is WM/County Hauling combined
    """
    match = re.search(r'VENDOR ACCOUNT NUMBER\s*(\w{3}-\d{5})', text, re.I)
    if match:
        return match.group(1)
    match = re.search(r'\b(\d{2}[A-Z]-\d{5})\b', text)
    if match:
        return match.group(1)
    # No-hyphen variant: 70A17595 in line-item context
    match = re.search(r'\b(\d{2}[A-Z]\d{5})\b', text)
    if match:
        val = match.group(1)
        return val[:3] + '-' + val[3:]  # Normalize to 70A-17595
    return None


# ============================================================
# PATTERN FIXES - February 2026
# Fixes for patterns identified in account_linkage analysis
# + NG Report Step 2 fixes (Feb 27, 2026)
# ============================================================

def _extract_jamaica_ash_fixed(text: str) -> Optional[str]:
    """Format: ACCOUNT# NNNNNN
    Example: 475394
    FIX: Previously marked as no_account, but invoices have ACCOUNT# field.
    """
    match = re.search(r'ACCOUNT#\s*(\d{5,7})', text, re.I)
    return match.group(1) if match else None


def _extract_mark_dunning_fixed(text: str) -> Optional[str]:
    """Format: ACCOUNT# NNNNNNN (same line or next line)
    Examples: 1398986, 1373624
    FIX: Original only checked next line; also match same line.
    """
    # Same line: ACCOUNT# 1398986
    match = re.search(r'ACCOUNT#\s*(\d{5,10})', text, re.I)
    if match:
        return match.group(1)
    # Next line fallback
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if 'ACCOUNT#' in line.upper():
            if i + 1 < len(lines):
                val = lines[i + 1].strip()
                if re.match(r'^\d{5,10}$', val):
                    return val
    return None


def _extract_parish_disposal_fixed(text: str) -> Optional[str]:
    """Format: ACCOUNT #\\nNG100124ROFL (alphanumeric, next line)
    Example: NG100124ROFL
    FIX: Previously marked as no_account, but invoices have ACCOUNT # field.
    """
    # Same line
    match = re.search(r'ACCOUNT\s*#\s*([A-Z0-9]{6,15})', text, re.I)
    if match:
        return match.group(1)
    # Next line
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if re.search(r'ACCOUNT\s*#', line, re.I):
            for j in range(i + 1, min(i + 4, len(lines))):
                val = lines[j].strip()
                if val and re.match(r'^[A-Z0-9]{4,15}$', val, re.I):
                    return val
    return None


def _extract_rp_waste(text: str) -> Optional[str]:
    """Format: Account #: NNNNN
    Example: 10077
    """
    match = re.search(r'Account\s*#:?\s*(\d{4,7})', text, re.I)
    return match.group(1) if match else None


def _extract_burgmeiers_fixed(text: str) -> Optional[str]:
    """Format: Customer ID NNN or Account # NNNNNNN
    Examples: 122, 1537213
    FIX: Original only matched Account # with 6-8 digits. Also match Customer ID.
    """
    # Customer ID (short numeric)
    match = re.search(r'Customer\s*ID\s*(\d{1,8})', text, re.I)
    if match:
        return match.group(1)
    # Account # (original pattern)
    match = re.search(r'(?:Account|Acct)\s*#:?\s*(\d{3,8})', text, re.I)
    if match:
        return match.group(1)
    return None


def _extract_casella_fixed(text: str) -> Optional[str]:
    """Format: CUSTOMER NUMBER __HS-NNNNN N (same line with underscores)
    Also: K/KI prefix, pure numeric, NN-NNNNN N
    Examples: HS-36966, K100008742, 81-39019 6
    FIX: Original didn't handle same-line with underscore prefix.
    """
    if 'PRICE CONFIRMATION' in text.upper():
        return None
    lines = text.split('\n')
    for i, line in enumerate(lines):
        upper = line.upper()
        if 'CUSTOMER NUMBER' in upper or 'CUST#:' in upper:
            # Same line: CUSTOMER NUMBER __HS-36966
            m = re.search(r'(?:CUSTOMER NUMBER|CUST#:?)\s*_*([A-Z]{2}-\d{4,6})\b', line, re.I)
            if m:
                return m.group(1).strip()
            # Same line: K/KI prefix
            m = re.search(r'(?:CUSTOMER NUMBER|CUST#:?)\s*_*(K[IR]?\d{7,9})', line, re.I)
            if m:
                return m.group(1).upper()
            # Same line: NN-NNNNN N
            m = re.search(r'(\d{2}-\d{5}\s*\d)', line)
            if m:
                return m.group(1).strip()
            # Next lines
            for j in range(i + 1, min(i + 6, len(lines))):
                val = lines[j].strip()
                if re.match(r'^K[IR]?\d{7,9}$', val, re.I):
                    return val.upper()
                if re.match(r'^\d{10}$', val):
                    return val
                m = re.search(r'(\d{2}-\d{5}\s*\d)', val)
                if m:
                    return m.group(1).strip()
    return None


def _extract_rumpke_fixed(text: str) -> Optional[str]:
    """Format: Account #: NNNNNNNNNN or Customer #: NNNNNNNNNN or Cust #:
    Examples: 0201174075, 4002536510
    FIX: Original only matched Customer #. Also match Account #, Cust #,
    and garbled OCR where label is unreadable but 10-digit number is present.
    """
    # Standard labels
    match = re.search(r'(?:Account|Customer|Cust)\s*#:?\s*(\d{10})', text, re.I)
    if match:
        return match.group(1)
    # Garbled label: look for 10-digit number before "For Service" or near top
    match = re.search(r':\s*(\d{10})\s+(?:For Service|For Billing)', text, re.I)
    if match:
        return match.group(1)
    # Standalone 10-digit near Access Code (Rumpke specific)
    match = re.search(r'(\d{10})\s+For Service', text, re.I)
    if match:
        return match.group(1)
    return None


def _extract_wb_waste_fixed(text: str) -> Optional[str]:
    """Format: CUSTOMER NO NNNNNNNNN
    Example: 150089231
    FIX: Previously marked as no_account, but invoices have CUSTOMER NO field.
    """
    match = re.search(r'CUSTOMER\s*NO\.?\s*(\d{6,12})', text, re.I)
    return match.group(1) if match else None


def _extract_waste_masters_fixed(text: str) -> Optional[str]:
    """Format: ACCOUNT NNNNNN-NNNN
    Example: 001608-0046
    FIX: Previously marked as no_account, but invoices have ACCOUNT field.
    """
    # With dash
    match = re.search(r'ACCOUNT\s+(\d{4,8}-\d{4})', text, re.I)
    if match:
        return match.group(1)
    # Pure numeric
    match = re.search(r'ACCOUNT\s+(\d{6,10})', text, re.I)
    if match:
        return match.group(1)
    return None


def _extract_atlantic_waste_fixed(text: str) -> Optional[str]:
    """Format: CUSTOMER NO BPNNNNNNN or Account Number NNNNNNNNN
    Examples: BP0000075, 921935800
    FIX: Original only matched Account Number + 9 digits. Also match CUSTOMER NO.
    Handles multiline: CUSTOMER NO\\nvalue on separate line
    """
    # Same line: CUSTOMER NO BP0000075
    match = re.search(r'CUSTOMER\s*NO\.?\s+([A-Z]{2}\d{5,9})', text, re.I)
    if match:
        return match.group(1)
    # Multiline: CUSTOMER NO on one line, value after other fields
    # e.g. "INVOICE NO INVOICE DATE ... CUSTOMER NO\nSWO... 12/09/2024 ... BP0000075"
    match = re.search(r'CUSTOMER\s*NO\b', text, re.I)
    if match:
        # Look for BP-prefixed value nearby (BP = specific prefix for this vendor)
        after = text[match.start():]
        m = re.search(r'\b(BP\d{5,9})\b', after)
        if m:
            return m.group(1)
    # Account Number (original)
    match = re.search(r'Account\s*Number\s*[:\n]?\s*(\d{9})', text, re.I)
    if match:
        return match.group(1)
    match = re.search(r'ActNbr:\s*(\d{9})', text)
    if match:
        return match.group(1)
    return None


def _extract_usa_waste_fixed(text: str) -> Optional[str]:
    """Format: ACCOUNT # NNNNNN or Customer ID: NN-NNNNN-NNNNN
    Examples: 004862, 18-59880-83006
    FIX: Original Customer ID pattern expected 1 digit prefix, actual has 1-2.
    """
    match = re.search(r'ACCOUNT\s*#\s*(\d{5,7})', text, re.I)
    if match:
        return match.group(1)
    match = re.search(r'Customer\s*ID:?\s*(\d{1,2}-\d{5}-\d{5})', text, re.I)
    if match:
        return match.group(1)
    return None


def _extract_unique_sanitation_fixed(text: str) -> Optional[str]:
    """Format: Account labeled on bill - user provided WAST342362
    Note: Pattern-based extraction may not work; rely on overrides.
    """
    match = re.search(r'(?:Account|Acct)\s*(?:#|No\.?|Number)?\s*:?\s*([A-Z]{4}\d{5,7})', text, re.I)
    return match.group(1) if match else None

def _extract_smarttrash_fixed(text: str) -> Optional[str]:
    """Format: C + 5 digits after Customer (with intervening fields)
    Examples: C02096, C02010
    FIX: Original pattern expected whitespace after Customer, but OCR has
    newlines and other fields between Customer and the account number.
    """
    # Allow any characters between Customer and the account
    match = re.search(r'Customer.*?(C\d{5})', text, re.IGNORECASE | re.DOTALL)
    return match.group(1) if match else None


def _extract_stryker_environmental_fixed(text: str) -> Optional[str]:
    """Format: Wasteology:UPS-SiteName or Wasteology:UPS (without hyphen)
    Examples: UPS-Mebane, UPS-Winston, UPS
    FIX: Original pattern required hyphen, but some invoices have just 'Wasteology:UPS'
    """
    # Allow optional hyphen and site name
    match = re.search(r'Wasteology:([A-Z]{2,5}(?:-[A-Za-z]+)?)', text)
    if match:
        return match.group(1).upper()
    # Also try with space after colon
    match = re.search(r'Wasteology:\s*([A-Z]{2,5}(?:-[A-Za-z]+)?)', text, re.IGNORECASE)
    return match.group(1).upper() if match else None


def _extract_ace_recycling_fixed(text: str) -> Optional[str]:
    """Format: 6-digit account number appears BEFORE column headers
    OCR structure: AMOUNT\\n801451\\nRECYCLING\\nINVOICE #\\nAMOUNT\\nACCOUNT #
    FIX: Values appear before their column headers in the OCR text.
    """
    text = str(text)
    # Pattern 1: 6-digit after dollar amount, before RECYCLING/DISPOSAL
    match = re.search(r'[\d,]+\.\d{2}\\n(\d{6})\\n(?:RECYCLING|DISPOSAL)', text)
    if match:
        return match.group(1)
    # Pattern 2: 6-digit before RECYCLING keyword
    match = re.search(r'(\d{6})\\nRECYCLING', text)
    if match:
        return match.group(1)
    # Pattern 3: Standard ACCOUNT # format as fallback
    match = re.search(r'ACCOUNT\s*#[\s\\n]*(\d{6})', text, re.IGNORECASE)
    return match.group(1) if match else None


# ============================================================
# VENDOR CONFIGURATIONS
# ============================================================

VENDOR_ADDITIONS_FEB2026 = {
    'Zero Waste': {
        'has_account': True,
        'format': 'NNNNN',
        'examples': ['24600'],
        'extract': _extract_zero_waste
    },
    'National Waste Services': {
        'has_account': True,
        'format': 'NNNNNNNX',
        'examples': ['1815350A'],
        'extract': _extract_national_waste_services
    },
    'Town Of Gilbert': {
        'has_account': True,
        'format': 'NNNNNNNN-NNNNNN',
        'examples': ['00555500-105245'],
        'extract': _extract_town_of_gilbert
    },
    'Townofgilbert': {
        'has_account': True,
        'format': 'NNNNNNNN-NNNNNN',
        'examples': ['00555500-105245'],
        'extract': _extract_town_of_gilbert
    },
    'Gilbert': {
        'has_account': True,
        'format': 'NNNNNNNN-NNNNNN',
        'examples': ['00555500-105245'],
        'extract': _extract_town_of_gilbert
    },
    'City Of Oxnard': {
        'has_account': True,
        'format': 'NNNNNN-NNNNNN',
        'examples': ['312315-304035'],
        'extract': _extract_city_of_oxnard
    },
    'SBC Waste': {
        'has_account': True,
        'format': 'NN-NNNNNNN',
        'examples': ['10-3323705'],
        'extract': _extract_sbc_waste
    },
    'Waste Disposal': {
        'has_account': True,
        'format': 'NNNNNNN',
        'examples': ['1787887'],
        'extract': _extract_waste_disposal_az
    },
    'Wastedisposalaz': {
        'has_account': True,
        'format': 'NNNNNNN',
        'examples': ['1787887'],
        'extract': _extract_waste_disposal_az
    },
    'Local Waste Solution': {
        'has_account': True,
        'format': 'NN-NNNNN N',
        'examples': ['01-11303 0'],
        'extract': _extract_lepage_sons
    },
    'Tate Services': {
        'has_account': True,
        'format': 'NNNNNN',
        'examples': ['010245'],
        'extract': _extract_tate_services
    },
    'KMG Hauling': {
        'has_account': True,
        'format': 'NNNNNN',
        'examples': ['006238'],
        'extract': _extract_kmg_hauling
    },
    'Waste Pro': {
        'has_account': True,
        'format': 'NNNNNN',
        'examples': ['231549'],
        'extract': _extract_waste_pro
    },
    'Earthwise Waste Solutions': {
        'has_account': True,
        'format': 'NNNNNNNNNNNN',
        'examples': ['127300001759'],
        'extract': _extract_earthwise_waste
    },
    'Modern Recycling': {
        'has_account': True,
        'format': 'NNNN',
        'examples': ['4179'],
        'extract': _extract_modern_recycling
    },
    'Check Sammy': {
        'has_account': True,
        'format': 'XXNNNNN',
        'examples': ['WH17455'],
        'extract': _extract_check_sammy
    },
    'Marborg': {
        'has_account': True,
        'format': 'N-NNNNNN-N',
        'examples': ['6-110313-6', '6-111598-1'],
        'extract': _extract_marborg
    },
    'EDCO Disposal': {
        'has_account': True,
        'format': 'NN-XX-NNNNNN',
        'examples': ['59-AN-354951'],
        'extract': _extract_edco_disposal
    },
    'Container Rentals': {
        'has_account': True,
        'format': 'NNNNNN (Work Order)',
        'examples': ['133701'],
        'extract': _extract_container_rentals
    },
    'Meridian Waste': {
        'has_account': True,
        'format': 'NN-NNNNNNN N',
        'examples': ['11-1193076 3'],
        'extract': _extract_meridian_waste
    },
    'Athens Services': {
        'has_account': True,
        'format': 'XX-NN',
        'examples': ['GM-89'],
        'extract': _extract_athens_services
    },
    'Aspen Waste': {
        'has_account': True,
        'format': 'N-NNNNN-N',
        'examples': ['1-51646-5'],
        'extract': _extract_aspen_waste
    },
    'Modern Disposal': {
        'has_account': True,
        'format': 'NNNN',
        'examples': ['4179'],
        'extract': _extract_modern_disposal
    },
    'Veit': {
        'has_account': True,
        'format': 'NNNNN',
        'examples': ['10735'],
        'extract': _extract_veit
    },
    'Veit Disposal': {
        'has_account': True,
        'format': 'NNNNN',
        'examples': ['10735'],
        'extract': _extract_veit
    },
    'USA Waste': {
        'has_account': True,
        'format': 'N-NNNNN-NNNNN',
        'examples': ['4-95068-35005'],
        'extract': _extract_usa_waste
    },
    'County Hauling': {
        'has_account': True,
        'format': 'NNA-NNNNN',
        'examples': ['70A-17595'],
        'extract': _extract_county_hauling
    },
    # Pattern fixes for existing vendors (override main engine)
    'SmartTrash': {
        'has_account': True,
        'format': 'CNNNNN',
        'examples': ['C02096', 'C02010', 'C01779'],
        'extract': _extract_smarttrash_fixed
    },
    'Stryker Environmental': {
        'has_account': True,
        'format': 'UPS-SITENAME or UPS',
        'examples': ['UPS-MEBANE', 'UPS-WINSTON', 'UPS'],
        'extract': _extract_stryker_environmental_fixed
    },
    'Ace Recycling': {
        'has_account': True,
        'format': 'NNNNNN',
        'examples': ['801451', '805945'],
        'extract': _extract_ace_recycling_fixed
    },
    # Aliases for filename variants
    'Zerowaste': {
        'has_account': True,
        'format': 'NNNNN',
        'examples': ['24600'],
        'extract': _extract_zero_waste
    },
    'Veit Disposal 2Nd Invoice': {
        'has_account': True,
        'format': 'NNNNN',
        'examples': ['10735'],
        'extract': _extract_veit
    },
    'Veit Disposal 3Rd Invoice': {
        'has_account': True,
        'format': 'NNNNN',
        'examples': ['10735'],
        'extract': _extract_veit
    },
    # --- NG Report Step 2 fixes (Feb 27, 2026) ---
    # Override main engine patterns that don't match NG invoice formats
    'Jamaica Ash': {
        'has_account': True,
        'format': 'NNNNNN',
        'examples': ['475394'],
        'extract': _extract_jamaica_ash_fixed
    },
    'Jamaica Ash & Rubbish': {
        'has_account': True,
        'format': 'NNNNNN',
        'examples': ['475394'],
        'extract': _extract_jamaica_ash_fixed
    },
    'Jamaicaash': {
        'has_account': True,
        'format': 'NNNNNN',
        'examples': ['475394'],
        'extract': _extract_jamaica_ash_fixed
    },
    'Mark Dunning': {
        'has_account': True,
        'format': 'NNNNNNN',
        'examples': ['1398986', '1373624'],
        'extract': _extract_mark_dunning_fixed
    },
    'Parish Disposal': {
        'has_account': True,
        'format': 'ALPHANUMERIC',
        'examples': ['NG100124ROFL'],
        'extract': _extract_parish_disposal_fixed
    },
    'RP Waste': {
        'has_account': True,
        'format': 'NNNNN',
        'examples': ['10077'],
        'extract': _extract_rp_waste
    },
    "Burgmeier's Hauling": {
        'has_account': True,
        'format': 'NNN or NNNNNNN',
        'examples': ['122', '1537213'],
        'extract': _extract_burgmeiers_fixed
    },
    'Casella': {
        'has_account': True,
        'format': 'XX-NNNNN or KNNNNNNNNN',
        'examples': ['HS-36966', 'K100008742', '81-39019 6'],
        'extract': _extract_casella_fixed
    },
    'Rumpke': {
        'has_account': True,
        'format': 'NNNNNNNNNN',
        'examples': ['0201174075', '4002536510'],
        'extract': _extract_rumpke_fixed
    },
    'WB Waste Solutions': {
        'has_account': True,
        'format': 'NNNNNNNNN',
        'examples': ['150089231'],
        'extract': _extract_wb_waste_fixed
    },
    'Waste Masters': {
        'has_account': True,
        'format': 'NNNNNN-NNNN',
        'examples': ['001608-0046'],
        'extract': _extract_waste_masters_fixed
    },
    'Atlantic Waste': {
        'has_account': True,
        'format': 'BPNNNNNNN or NNNNNNNNN',
        'examples': ['BP0000075', '921935800'],
        'extract': _extract_atlantic_waste_fixed
    },
    'USA Waste': {
        'has_account': True,
        'format': 'NN-NNNNN-NNNNN',
        'examples': ['18-59880-83006', '4-95068-35005'],
        'extract': _extract_usa_waste_fixed
    },
    'Unique Sanitation': {
        'has_account': True,
        'format': 'XXXXNNNNNNN',
        'examples': ['WAST342362'],
        'extract': _extract_unique_sanitation_fixed
    },
    'Choicecontractors': {
        'has_account': False,
        'format': None,
        'examples': [],
        'extract': lambda x: None
    },
    # --- NG broker vendor aliases (Mar 2026) ---
    'Waste Disposal AZ': {
        'has_account': True,
        'format': 'NNNNNNN',
        'examples': ['1787887'],
        'extract': _extract_waste_disposal_az
    },
    'Checksammy': {
        'has_account': True,
        'format': 'XXNNNNN',
        'examples': ['WH17455'],
        'extract': _extract_check_sammy
    },
    'Vanderlind Recycling': {
        'has_account': True,
        'format': 'NNNNNN (Work Order)',
        'examples': ['133701'],
        'extract': _extract_container_rentals
    },
    'RP Waste Solutions': {
        'has_account': True,
        'format': 'NNNNN',
        'examples': ['10077'],
        'extract': _extract_rp_waste
    },
    'Arc of The St Johns': {
        'has_account': False,
        'format': None,
        'examples': [],
        'extract': lambda x: None
    },
    'C & M Topsoil': {
        'has_account': False,
        'format': None,
        'examples': [],
        'extract': lambda x: None
    },
    'Master Pac Services': {
        'has_account': False,
        'format': None,
        'examples': [],
        'extract': lambda x: None
    },
    'PSI Waste Equipment': {
        'has_account': False,
        'format': None,
        'examples': [],
        'extract': lambda x: None
    },
    'Momentum Recycling': {
        'has_account': False,
        'format': None,
        'examples': [],
        'extract': lambda x: None
    },
}


def register_additions(vendor_accounts: dict):
    """Register Feb 2026 additions to the main VENDOR_ACCOUNTS dict."""
    vendor_accounts.update(VENDOR_ADDITIONS_FEB2026)
