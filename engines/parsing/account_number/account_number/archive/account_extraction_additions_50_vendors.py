"""
Account Extraction Additions v4
50 New Vendor Configurations

Add these to account_extraction_engine_v3.py
"""
import re
from typing import Optional


# ============================================================
# NEW VENDOR EXTRACTION FUNCTIONS (50 vendors)
# ============================================================

# --- BATCH 1: Vendors 1-10 ---

def _extract_city_of_meridian(text: str) -> Optional[str]:
    """Format: NNNNNNNN-NN (utility account format)
    Examples: 99011222-01, 99011234-01
    """
    # Pattern 1: Account: NNNNNNNN-NN
    match = re.search(r'Account[:\s#]*(\d{8}-\d{2})', text)
    if match:
        return match.group(1)
    # Pattern 2: Account No.: NNNNNNNN-NN  
    match = re.search(r'Account\s*No\.?:?\s*(\d{8}-\d{2})', text)
    if match:
        return match.group(1)
    return None


def _extract_blue_diamond_disposal(text: str) -> Optional[str]:
    """Format: NNNNN (5-digit customer number)
    Examples: 30239
    """
    lines = text.split('\\n')
    for i, line in enumerate(lines):
        if 'CUSTOMER NO' in line.upper():
            # Same line extraction
            match = re.search(r'CUSTOMER\s*NO\.?\s*(\d{4,6})', line, re.I)
            if match:
                return match.group(1)
            # Check next lines
            for j in range(i+1, min(i+5, len(lines))):
                val = lines[j].strip()
                if re.match(r'^\d{4,6}$', val):
                    return val
    return None


def _extract_valley_vista(text: str) -> Optional[str]:
    """Format: VV-NNNNNN N (with VV prefix)
    Examples: VV-478887 7, VV-478891 9
    """
    # Pattern: VV-NNNNNN N
    match = re.search(r'(VV-\d{6}\s*\d)', text)
    if match:
        return match.group(1).strip()
    # Alternative: Account Number followed by VV pattern
    match = re.search(r'Account\s*Number[:\s]*(VV-\d{6}\s*\d)', text, re.I)
    if match:
        return match.group(1).strip()
    return None


def _extract_ssw_frontload(text: str) -> Optional[str]:
    """Format: NNNN (4-digit account)
    Examples: 6215, 5617
    Uses TrashBilling system
    """
    # Pattern: Acct# NNNN
    match = re.search(r'Acct#?\s*(\d{4,6})', text)
    if match:
        return match.group(1)
    return None


def _extract_velpen_trucking(text: str) -> Optional[str]:
    """Format: NNNNNN (6-digit with leading zeros)
    Examples: 006509, 052698
    Uses TrashBilling system
    """
    # Pattern: account number with this hauler is NNNNNN
    match = re.search(r'account\s*number\s*(?:with\s*this\s*hauler\s*is)?\s*(\d{6})', text, re.I)
    if match:
        return match.group(1)
    # TrashBilling ID pattern
    match = re.search(r'ID#:\s*\d+(\d{6})', text)
    if match:
        return match.group(1)
    return None


def _extract_gotta_go_waste(text: str) -> Optional[str]:
    """Format: NNNN (4-digit customer number)
    Examples: 7933
    Pattern: Customer appears in header row, value appears several lines later
    """
    lines = text.split('\\n')
    for i, line in enumerate(lines):
        if line.strip() == 'Customer':
            # Value appears after Site, PO Number, Invoice#, Page, Date - typically 5-10 lines later
            for j in range(i+1, min(i+12, len(lines))):
                val = lines[j].strip()
                if re.match(r'^\d{4,5}$', val):
                    return val
    return None


def _extract_louisiana_waste(text: str) -> Optional[str]:
    """Format: NNNN (4-digit account)
    Examples: 3704
    """
    # Pattern: ACCOUNT # followed by 4-digit
    match = re.search(r'ACCOUNT\s*#\s*(\d{4,6})', text, re.I)
    if match:
        return match.group(1)
    lines = text.split('\\n')
    for i, line in enumerate(lines):
        if 'ACCOUNT #' in line.upper():
            for j in range(i+1, min(i+5, len(lines))):
                val = lines[j].strip()
                if re.match(r'^\d{4,6}$', val):
                    return val
    return None


def _extract_abc_waste(text: str) -> Optional[str]:
    """Format: NN-NNNNNN N or NN-NNNNNNN
    Examples: 10-339800 4, 10-3471256
    """
    # Pattern 1: NN-NNNNNN N (with trailing digit)
    match = re.search(r'Account\s*No\.?\s*(\d{2}-\d{6,7}\s*\d?)', text, re.I)
    if match:
        return match.group(1).strip()
    # Pattern 2: Just the format
    match = re.search(r'(\d{2}-\d{6,7}\s*\d?)', text)
    if match:
        return match.group(1).strip()
    return None


def _extract_smith_creek(text: str) -> Optional[str]:
    """Format: WAST0004 style alphanumeric code
    Examples: WAST0004
    Note: OCR has literal \\n which breaks word boundaries
    """
    # Pattern: WAST + 4 digits (specific to this vendor)
    match = re.search(r'(WAST\d{4})', text)
    if match:
        return match.group(1)
    # Pattern 2: Generic 4-letter + 4-digit code
    match = re.search(r'([A-Z]{4}\d{4})', text)
    if match:
        return match.group(1)
    return None


def _extract_jlt_trucking(text: str) -> Optional[str]:
    """Format: NNNNNNN (7-digit account)
    Examples: 1001434
    Pattern: ACCOUNT #\n value on next line
    """
    lines = text.split('\\n')
    for i, line in enumerate(lines):
        if 'ACCOUNT #' in line.upper() or 'ACCOUNT#' in line.upper():
            for j in range(i+1, min(i+5, len(lines))):
                val = lines[j].strip()
                if re.match(r'^\d{6,8}$', val):
                    return val
    return None


# --- BATCH 2: Vendors 11-20 ---

def _extract_liberty_disposal(text: str) -> Optional[str]:
    """Format: NNNNXX (4-digit + 2 letters) or NNNNNN
    Examples: 2476TU, 019022
    """
    # Pattern 1: ACCOUNT NO with alphanumeric
    match = re.search(r'ACCOUNT\s*NO\.?\s*(\d{4,6}[A-Z]{0,2})', text, re.I)
    if match:
        return match.group(1)
    # Pattern 2: CUSTOMER followed by number
    match = re.search(r'CUSTOMER\s+(\d{6})', text)
    if match:
        return match.group(1)
    return None


def _extract_zarc_recycling(text: str) -> Optional[str]:
    """Format: NNN (3-4 digit customer ID)
    Examples: 979, 992
    """
    match = re.search(r'Customer\s*ID:\s*(\d{3,5})', text, re.I)
    if match:
        return match.group(1)
    return None


def _extract_1800_got_junk(text: str) -> Optional[str]:
    """Format: NNN (3-4 digit customer ID)
    Examples: 990
    Two formats:
    1. Values before headers: INV258126\\n12/16/2025\\n990\\n...\\nInvoice Number:\\nDate:\\nCustomer ID:
    2. Values after headers: Invoice Number:\\nDate:\\nCustomer ID:\\n...\\nINV251246\\n11/26/2025\\n990
    """
    # Pattern 1: Inline format
    match = re.search(r'Customer\s*ID:\s*(\d{3,5})', text, re.I)
    if match:
        return match.group(1)
    
    lines = text.split('\\n')
    
    # Find Customer ID: position in headers
    customer_id_idx = None
    for i, line in enumerate(lines):
        if 'Customer ID:' in line:
            customer_id_idx = i
            break
    
    if customer_id_idx is None:
        return None
    
    # Determine if values are before or after headers
    # Look for Invoice Number: header
    invoice_header_idx = None
    for i, line in enumerate(lines):
        if 'Invoice Number:' in line:
            invoice_header_idx = i
            break
    
    if invoice_header_idx is not None:
        # Calculate offset from Invoice Number to Customer ID (should be 2)
        offset = customer_id_idx - invoice_header_idx
        
        # Pattern 2: Values AFTER headers - look for where values start
        # Find first INV pattern after headers
        for i in range(customer_id_idx + 1, min(customer_id_idx + 20, len(lines))):
            if lines[i].strip().startswith('INV'):
                # Found values section - Customer ID is at same offset from here
                value_idx = i + offset
                if value_idx < len(lines):
                    val = lines[value_idx].strip()
                    if re.match(r'^\d{3,4}$', val):
                        return val
        
        # Pattern 3: Values BEFORE headers
        for j in range(max(0, invoice_header_idx - 10), invoice_header_idx):
            if lines[j].strip().startswith('INV'):
                # Found values section before headers
                value_idx = j + offset
                if value_idx < len(lines):
                    val = lines[value_idx].strip()
                    if re.match(r'^\d{3,4}$', val):
                        return val
    
    return None


def _extract_ryland_environmental(text: str) -> Optional[str]:
    """Format: XXNNNN (2 letters + 4 digits)
    Examples: AC4946
    """
    match = re.search(r'CUSTOMER\s*NO\.?\s*([A-Z]{2}\d{4,6})', text, re.I)
    if match:
        return match.group(1)
    # Alternative: Customer No on separate line
    lines = text.split('\\n')
    for i, line in enumerate(lines):
        if 'CUSTOMER NO' in line.upper():
            for j in range(i+1, min(i+5, len(lines))):
                val = lines[j].strip()
                if re.match(r'^[A-Z]{2}\d{4,6}$', val):
                    return val
    return None


def _extract_independent_recycling(text: str) -> Optional[str]:
    """Format: NNNN (4-digit customer number)
    Examples: 5905
    """
    lines = text.split('\\n')
    for i, line in enumerate(lines):
        if 'CUSTOMER NO' in line.upper():
            for j in range(i+1, min(i+6, len(lines))):
                val = lines[j].strip()
                if re.match(r'^\d{4,6}$', val):
                    return val
    return None


def _extract_moore_coal(text: str) -> Optional[str]:
    """Format: NNNN (4-digit customer number)
    Examples: 4808
    """
    lines = text.split('\\n')
    for i, line in enumerate(lines):
        if 'CUSTOMER NO' in line.upper():
            for j in range(i+1, min(i+6, len(lines))):
                val = lines[j].strip()
                if re.match(r'^\d{4,6}$', val):
                    return val
    return None


def _extract_honolulu_disposal(text: str) -> Optional[str]:
    """Format: NNNNNNNNNN (10-digit account)
    Examples: 2131885000, 2131935400
    """
    # Pattern: ACCOUNT followed by 10-digit
    match = re.search(r'ACCOUNT\s*(\d{10})', text, re.I)
    if match:
        return match.group(1)
    # Alternative: ACCT # pattern
    match = re.search(r'ACCT\s*#:?\s*(\d{10})', text, re.I)
    if match:
        return match.group(1)
    return None


def _extract_pelican_waste(text: str) -> Optional[str]:
    """Format: NNNNNN (6-digit customer number with leading zeros)
    Examples: 031803, 026634, 029610
    Pattern: Customer No. followed by headers, then 6-digit value on next line
    """
    lines = text.split('\\n')
    for i, line in enumerate(lines):
        if 'Customer No' in line:
            # Check next few lines for 6-digit number
            for j in range(i+1, min(i+6, len(lines))):
                val = lines[j].strip()
                # Match 6-digit at start of line (may have more text after)
                match = re.match(r'^(\d{6})\b', val)
                if match:
                    return match.group(1)
    return None


def _extract_great_waste(text: str) -> Optional[str]:
    """Format: NNNNNNN (7-digit account number)
    Examples: 1129190, 1129200
    Pattern: Account Number\nInvoice Date\n1129190
    """
    lines = text.split('\\n')
    for i, line in enumerate(lines):
        if 'Account Number' in line:
            # Value is typically 2 lines after header (after Invoice Date)
            for j in range(i+1, min(i+6, len(lines))):
                val = lines[j].strip()
                if re.match(r'^\d{6,8}$', val):
                    return val
    # Also check ActNbr pattern
    match = re.search(r'ActNbr:\s*(\d{7})', text)
    if match:
        return match.group(1)
    return None


def _extract_modern_recycling(text: str) -> Optional[str]:
    """Format: NNNNN (5-digit customer number)
    Examples: 53262
    Pattern: Customer Number:\n053262-0003\n53262
    """
    lines = text.split('\\n')
    for i, line in enumerate(lines):
        if 'Customer Number' in line:
            # Check next few lines for 5-6 digit number
            for j in range(i+1, min(i+6, len(lines))):
                val = lines[j].strip()
                # Match standalone 5-6 digit number
                if re.match(r'^\d{5,6}$', val):
                    return val
                # Match in format NNNNNN-NNNN (take first part)
                match = re.match(r'^(\d{5,6})-\d+$', val)
                if match:
                    return match.group(1)
    return None


# --- BATCH 3: Vendors 21-30 ---

def _extract_redgate_disposal(text: str) -> Optional[str]:
    """Format: XNNNN (letter + 4 digits)
    Examples: C8451, C8452, C8498
    Pattern: Account #\nCNNNN at end of document
    """
    lines = text.split('\\n')
    # Search from end backwards
    for i in range(len(lines)-1, -1, -1):
        if 'Account #' in lines[i]:
            # Check next line
            if i+1 < len(lines):
                val = lines[i+1].strip()
                if re.match(r'^[A-Z]\d{4,5}$', val):
                    return val
    # Also try finding pattern directly
    match = re.search(r'Account\s*#\\n([A-Z]\d{4,5})', text)
    if match:
        return match.group(1)
    return None


def _extract_wg_waste(text: str) -> Optional[str]:
    """Format: NNNNNN (6-digit account)
    Examples: 203287, 202636
    Pattern: ACCOUNT#\n203287
    """
    lines = text.split('\\n')
    for i, line in enumerate(lines):
        if 'ACCOUNT#' in line.upper() or 'ACCT#' in line.upper():
            # Check if value is on same line
            match = re.search(r'(?:ACCOUNT#|ACCT#)\s*(\d{6})', line, re.I)
            if match:
                return match.group(1)
            # Check next line
            if i+1 < len(lines):
                val = lines[i+1].strip()
                if re.match(r'^\d{6}$', val):
                    return val
    return None


def _extract_community_waste(text: str) -> Optional[str]:
    """Format: Multiple formats
    - NN-NNNNNN N (10-271295 7)
    - NNNNN (21105)
    - NNNNNN (102167) 
    - NNNNNN-NNN (107441-109)
    """
    # Pattern 1: ACCOUNT # followed by value in columnar format
    lines = text.split('\\n')
    for i, line in enumerate(lines):
        if 'ACCOUNT #' in line.upper() or 'ACCOUNT#' in line.upper():
            # Check next few lines for account number
            for j in range(i+1, min(i+5, len(lines))):
                val = lines[j].strip()
                # Format: NNNNNN-NNN
                if re.match(r'^\d{5,6}-\d{2,3}$', val):
                    return val
                # Format: NNNNN or NNNNNN (5-6 digits)
                if re.match(r'^\d{5,6}$', val):
                    return val
                # Format: NN-NNNNNN N
                m = re.match(r'^(\d{2}-\d{6}\s*\d)$', val)
                if m:
                    return m.group(1).strip()
    # Pattern 2: Direct NN-NNNNNN N pattern
    match = re.search(r'(\d{2}-\d{6}\s*\d)', text)
    if match:
        return match.group(1).strip()
    return None


def _extract_city_of_boise(text: str) -> Optional[str]:
    """Format: NNNNNNNNNNNNNNN (15-digit account)
    Examples: 057576800095407, 059147800347545
    """
    match = re.search(r'Account\s*#:\s*(\d{15})', text, re.I)
    if match:
        return match.group(1)
    return None


def _extract_western_disposal(text: str) -> Optional[str]:
    """Format: NNNNNN (6-digit account)
    Examples: 123825, 121004, 137542
    Pattern: Account #\nBilling Date\nDue Date\n123825
    """
    lines = text.split('\\n')
    for i, line in enumerate(lines):
        if 'Account #' in line or 'Account#' in line:
            # Value is typically 3 lines after header
            for j in range(i+1, min(i+8, len(lines))):
                val = lines[j].strip()
                if re.match(r'^\d{6}$', val):
                    return val
    return None


def _extract_city_of_jackson(text: str) -> Optional[str]:
    """Format: Multiple formats
    - NC: NNNNNN-NNNNN (203809-21438)
    - TN: NNNNN (48749) - 5-digit customer number
    - FL: NNNNNN-NNNNNN (727113-633339)
    """
    # Pattern 1: FL format inline - CUSTOMER NUMBER: NNNNNN-NNNNNN
    match = re.search(r'CUSTOMER\s*NUMBER:\s*(\d{6}-\d{6})', text, re.I)
    if match:
        return match.group(1)
    
    # Pattern 2: NC format with hyphen - inline
    match = re.search(r'Account\s*Number\s*(\d{6}-\d{5})', text, re.I)
    if match:
        return match.group(1)
    # Pattern 3: NC columnar - Account Number on one line, value on next
    lines = text.split('\\n')
    for i, line in enumerate(lines):
        if 'Account Number' in line:
            for j in range(i+1, min(i+5, len(lines))):
                val = lines[j].strip()
                m = re.match(r'^(\d{6}-\d{5})$', val)
                if m:
                    return m.group(1)
    # Pattern 4: TN format - CUSTOMER NO columnar with 5-7 digit
    for i, line in enumerate(lines):
        if 'CUSTOMER NO' in line.upper():
            for j in range(i+1, min(i+10, len(lines))):
                val = lines[j].strip()
                if re.match(r'^\d{5,7}$', val):
                    return val
    return None


def _extract_gulf_coast_containers(text: str) -> Optional[str]:
    """Format: NNNN (4-digit customer number)
    Examples: 3401
    """
    lines = text.split('\\n')
    for i, line in enumerate(lines):
        if 'CUSTOMER NO' in line.upper():
            for j in range(i+1, min(i+5, len(lines))):
                val = lines[j].strip()
                if re.match(r'^\d{4,6}$', val):
                    return val
    return None


def _extract_amwaste(text: str) -> Optional[str]:
    """Format: NNNNNN (6-digit account)
    Examples: 095565, 123776
    """
    match = re.search(r'ACCOUNT\s*#:\s*(\d{6})', text, re.I)
    if match:
        return match.group(1)
    return None


def _extract_lexington_site_services(text: str) -> Optional[str]:
    """Format: NNNNNNNNN (9-digit account number)
    Examples: 220009602, 218757601
    Pattern: Account Number\n220009602
    """
    # Pattern 1: Inline format
    match = re.search(r'Account\s*Number\s*(\d{9})', text, re.I)
    if match:
        return match.group(1)
    # Pattern 2: Columnar format
    lines = text.split('\\n')
    for i, line in enumerate(lines):
        if 'Account Number' in line:
            for j in range(i+1, min(i+5, len(lines))):
                val = lines[j].strip()
                if re.match(r'^\d{9}$', val):
                    return val
    return None


def _extract_gateway_disposal(text: str) -> Optional[str]:
    """Format: NNNNNN (6-digit account)
    Examples: 718227, 777815
    Pattern: ACCOUNT#\n718227 or ACCT#718227
    """
    # Pattern 1: ACCT# inline (no space)
    match = re.search(r'ACCT#(\d{6})', text, re.I)
    if match:
        return match.group(1)
    # Pattern 2: ACCOUNT# with optional space
    match = re.search(r'ACCOUNT#\s*(\d{6})', text, re.I)
    if match:
        return match.group(1)
    # Pattern 3: Columnar format
    lines = text.split('\\n')
    for i, line in enumerate(lines):
        if 'ACCOUNT#' in line.upper():
            for j in range(i+1, min(i+3, len(lines))):
                val = lines[j].strip()
                if re.match(r'^\d{6}$', val):
                    return val
    return None


# --- BATCH 4: Vendors 31-40 ---

def _extract_tk_trash(text: str) -> Optional[str]:
    """Format: NN-NNNNNN N (Trash Kans format)
    Examples: 75-602470 5, 75-606004 8
    """
    match = re.search(r'Customer\s*#\s*(\d{2}-\d{6}\s*\d)', text, re.I)
    if match:
        return match.group(1).strip()
    return None


def _extract_recology(text: str) -> Optional[str]:
    """Format: A############ or NNNNNNNNNN
    Examples: A0040314948, 1070055251
    """
    # Pattern 1: A + digits
    match = re.search(r'ACCOUNT\s*(?:NO\.?)?\s*(A\d{10,13})', text, re.I)
    if match:
        return match.group(1)
    # Pattern 2: Pure numeric
    match = re.search(r'Account\s*No\.?\s*(\d{10})', text, re.I)
    if match:
        return match.group(1)
    return None


def _extract_jk_trash(text: str) -> Optional[str]:
    """Format: NNNNNN (6-digit account)
    Examples: 585055, 585077, 585066
    Pattern: ACCOUNT#\n585055
    """
    lines = text.split('\\n')
    for i, line in enumerate(lines):
        if 'ACCOUNT#' in line.upper():
            # Check next line
            if i+1 < len(lines):
                val = lines[i+1].strip()
                if re.match(r'^\d{6}$', val):
                    return val
    # Also try ACCT# pattern
    match = re.search(r'ACCT#\s*(\d{6})', text, re.I)
    if match:
        return match.group(1)
    return None


def _extract_clean_slate(text: str) -> Optional[str]:
    """Format: NNNNN (5-digit account)
    Examples: 10335
    Two formats:
    1. Receipt: Clean Slate\\nReceipt\\n35224\\n10335 (values at top)
    2. Invoice: Invoice #:\\nAccount #:\\n...\\n37514\\n10335 (values after headers)
    """
    lines = text.split('\\n')
    
    # Pattern 1: Receipt format - look for 5-digit number near top after header numbers
    if 'Receipt' in text:
        for i, line in enumerate(lines[:10]):
            val = line.strip()
            if re.match(r'^\d{5}$', val):
                return val
    
    # Pattern 2: Invoice format - find Account # header, then values
    for i, line in enumerate(lines):
        if 'Account #:' in line or 'Account #' in line:
            # Values may be before (columnar) or after
            # Try inline first
            match = re.search(r'Account\s*#:\s*(\d{5,6})', line, re.I)
            if match:
                return match.group(1)
            # Look for value rows - find 5-digit numbers
            for j in range(i+1, min(i+15, len(lines))):
                val = lines[j].strip()
                if re.match(r'^\d{5}$', val):
                    return val
    
    return None


def _extract_olympic_compactor_rentals(text: str) -> Optional[str]:
    """Format: NN-NNNNNNN (with leading zeros)
    Examples: 01-0080240, 01-0002543
    """
    match = re.search(r'CUSTOMER\s*NO\.?:?\s*(\d{2}-\d{7})', text, re.I)
    if match:
        return match.group(1)
    # Also check Customer Number:
    match = re.search(r'Customer\s*Number:?\s*(\d{2}-\d{7})', text, re.I)
    if match:
        return match.group(1)
    return None


def _extract_walker_lake_disposal(text: str) -> Optional[str]:
    """Format: NNN (3-digit account)
    Examples: 375
    """
    match = re.search(r'Account\s*#\s*(\d{3,5})', text, re.I)
    if match:
        return match.group(1)
    return None


def _extract_trident_waste(text: str) -> Optional[str]:
    """Format: NN-NNNNN N
    Examples: 01-35884 5, 01-29316 6
    """
    match = re.search(r'Account\s*No\.?\s*(\d{2}-\d{5}\s*\d)', text, re.I)
    if match:
        return match.group(1).strip()
    return None


def _extract_blue_hills_environmental(text: str) -> Optional[str]:
    """Format: NNNNNN (6-digit account)
    Examples: 112837, 112832
    """
    match = re.search(r'(?:Account\s*#?|AccountNumber):\s*(\d{6})', text, re.I)
    if match:
        return match.group(1)
    return None


def _extract_ohio_valley_waste(text: str) -> Optional[str]:
    """Format: NN NNNNNNN N (with spaces)
    Examples: 90 0005041 0
    Also: NN - NNNN
    """
    match = re.search(r'Customer\s*Number:\s*(\d{2}\s*\d{7}\s*\d)', text, re.I)
    if match:
        return match.group(1).strip()
    # Alternative: Account number pattern
    match = re.search(r'Account\s*number:\s*(\d{2}\s*-\s*\d{4})', text, re.I)
    if match:
        return match.group(1).replace(' ', '')
    return None


def _extract_city_waste(text: str) -> Optional[str]:
    """Format: NN-NNNN N
    Examples: 10-5648 0, 10-5909 6
    """
    match = re.search(r'Customer\s*#:\s*(\d{2}-\d{4}\s*\d)', text, re.I)
    if match:
        return match.group(1).strip()
    return None


# --- BATCH 5: Vendors 41-50 ---

def _extract_vogel_disposal(text: str) -> Optional[str]:
    """Format: NN NNNNNNN N (with spaces)
    Examples: 02 0026280 6
    """
    match = re.search(r'Customer\s*Number:\s*(\d{2}\s+\d{7}\s+\d)', text, re.I)
    if match:
        return match.group(1)
    return None


def _extract_willscot(text: str) -> Optional[str]:
    """Format: NNNNNNNN (8-digit customer number)
    Examples: 10464335
    Pattern: Customer #:\n10464335 or in header row
    """
    # Pattern 1: Customer #: followed by value
    match = re.search(r'Customer\s*#:\s*(\d{8})', text, re.I)
    if match:
        return match.group(1)
    # Pattern 2: Check columnar format
    lines = text.split('\\n')
    for i, line in enumerate(lines):
        if 'Customer #' in line and 'Bill to' in line:
            # Header row - look for value row
            for j in range(i+1, min(i+10, len(lines))):
                val = lines[j].strip()
                if re.match(r'^\d{8}$', val):
                    return val
    # Pattern 3: Customer No: format
    match = re.search(r'Customer\s*No:\s*(\d{8})', text, re.I)
    if match:
        return match.group(1)
    return None


def _extract_boro_wide(text: str) -> Optional[str]:
    """Format varies - search for account patterns"""
    match = re.search(r'Account\s*#:?\s*(\d{5,8})', text, re.I)
    if match:
        return match.group(1)
    return None


def _extract_direct_waste_services(text: str) -> Optional[str]:
    """Format: NNNNNN"""
    match = re.search(r'Account\s*#:?\s*(\d{5,8})', text, re.I)
    if match:
        return match.group(1)
    return None


def _extract_cards_mo(text: str) -> Optional[str]:
    """Format varies"""
    match = re.search(r'Account\s*#:?\s*(\d{5,8})', text, re.I)
    if match:
        return match.group(1)
    return None


def _extract_chrin_hauling(text: str) -> Optional[str]:
    """Format: typically 6-digit"""
    match = re.search(r'(?:Account|Customer)\s*(?:#|No\.?)?\s*:?\s*(\d{5,8})', text, re.I)
    if match:
        return match.group(1)
    return None


def _extract_roll_off_systems(text: str) -> Optional[str]:
    """Format varies"""
    match = re.search(r'Account\s*#:?\s*(\d{5,8})', text, re.I)
    if match:
        return match.group(1)
    return None


def _extract_lakeshore_recycling(text: str) -> Optional[str]:
    """Format: typically numeric"""
    match = re.search(r'(?:Account|Customer)\s*(?:#|No\.?)?\s*:?\s*(\d{5,10})', text, re.I)
    if match:
        return match.group(1)
    return None


def _extract_waste_services_llc(text: str) -> Optional[str]:
    """Format varies"""
    match = re.search(r'Account\s*#:?\s*(\d{5,8})', text, re.I)
    if match:
        return match.group(1)
    return None


def _extract_cooks_wastepaper(text: str) -> Optional[str]:
    """Format varies"""
    match = re.search(r'(?:Account|Customer)\s*(?:#|No\.?)?\s*:?\s*(\d{4,8})', text, re.I)
    if match:
        return match.group(1)
    return None


# ============================================================
# VENDOR ACCOUNTS CONFIGURATION
# ============================================================

NEW_VENDOR_ACCOUNTS = {
    # Batch 1: Vendors with clear account formats
    'City of Meridian': {
        'has_account': True,
        'format': 'NNNNNNNN-NN',
        'examples': ['99011222-01', '99011234-01'],
        'extract': _extract_city_of_meridian
    },
    'Blue Diamond Disposal': {
        'has_account': True,
        'format': 'NNNNN',
        'examples': ['30239'],
        'extract': _extract_blue_diamond_disposal
    },
    'Valley Vista': {
        'has_account': True,
        'format': 'VV-NNNNNN N',
        'examples': ['VV-478887 7', 'VV-478891 9'],
        'extract': _extract_valley_vista
    },
    'SSW Frontload': {
        'has_account': True,
        'format': 'NNNN',
        'examples': ['6215', '5617'],
        'extract': _extract_ssw_frontload
    },
    'Velpen Trucking': {
        'has_account': True,
        'format': 'NNNNNN',
        'examples': ['006509', '052698'],
        'extract': _extract_velpen_trucking
    },
    'Gotta Go Waste': {
        'has_account': True,
        'format': 'NNNN',
        'examples': ['7933'],
        'extract': _extract_gotta_go_waste
    },
    'Louisiana Waste': {
        'has_account': True,
        'format': 'NNNN',
        'examples': ['3704'],
        'extract': _extract_louisiana_waste
    },
    'ABC Waste': {
        'has_account': True,
        'format': 'NN-NNNNNN N',
        'examples': ['10-339800 4', '10-3471256'],
        'extract': _extract_abc_waste
    },
    'Smith Creek': {
        'has_account': True,
        'format': 'XXXXNNNN',
        'examples': ['WAST0004'],
        'extract': _extract_smith_creek
    },
    'JLT Trucking': {
        'has_account': True,
        'format': 'NNNNNNN',
        'examples': ['1001434'],
        'extract': _extract_jlt_trucking
    },
    
    # Batch 2
    'Liberty Disposal': {
        'has_account': True,
        'format': 'NNNNXX or NNNNNN',
        'examples': ['2476TU', '019022'],
        'extract': _extract_liberty_disposal
    },
    'ZARC Recycling': {
        'has_account': True,
        'format': 'NNN',
        'examples': ['979', '992'],
        'extract': _extract_zarc_recycling
    },
    '1-800-Got-Junk': {
        'has_account': True,
        'format': 'NNN',
        'examples': ['990'],
        'extract': _extract_1800_got_junk
    },
    'Ryland Environmental': {
        'has_account': True,
        'format': 'XXNNNN',
        'examples': ['AC4946'],
        'extract': _extract_ryland_environmental
    },
    'Independent Recycling': {
        'has_account': True,
        'format': 'NNNN',
        'examples': ['5905'],
        'extract': _extract_independent_recycling
    },
    'Moore Coal': {
        'has_account': True,
        'format': 'NNNN',
        'examples': ['4808'],
        'extract': _extract_moore_coal
    },
    'Honolulu Disposal': {
        'has_account': True,
        'format': 'NNNNNNNNNN',
        'examples': ['2131885000', '2131935400'],
        'extract': _extract_honolulu_disposal
    },
    'Pelican Waste': {
        'has_account': True,
        'format': 'NNNNNN',
        'examples': ['031803', '026634'],
        'extract': _extract_pelican_waste
    },
    'Great Waste': {
        'has_account': True,
        'format': 'NNNNNNN',
        'examples': ['1129190'],
        'extract': _extract_great_waste
    },
    'Modern Recycling': {
        'has_account': True,
        'format': 'NNNNN',
        'examples': ['53262'],
        'extract': _extract_modern_recycling
    },
    
    # Batch 3
    'Redgate Disposal': {
        'has_account': True,
        'format': 'XNNNN',
        'examples': ['C8451', 'C8452'],
        'extract': _extract_redgate_disposal
    },
    'WG Waste': {
        'has_account': True,
        'format': 'NNNNNN',
        'examples': ['203287'],
        'extract': _extract_wg_waste
    },
    'Community Waste': {
        'has_account': True,
        'format': 'NN-NNNNNN N',
        'examples': ['10-271295 7', '21105'],
        'extract': _extract_community_waste
    },
    'City of Boise': {
        'has_account': True,
        'format': 'NNNNNNNNNNNNNNN',
        'examples': ['057576800095407', '059147800347545'],
        'extract': _extract_city_of_boise
    },
    'Western Disposal': {
        'has_account': True,
        'format': 'NNNNNN',
        'examples': ['123825', '121004'],
        'extract': _extract_western_disposal
    },
    'City of Jackson': {
        'has_account': True,
        'format': 'NNNNNN-NNNNN or NNNNNNN',
        'examples': ['203809-21438', '7310746'],
        'extract': _extract_city_of_jackson
    },
    'Gulf Coast Containers': {
        'has_account': True,
        'format': 'NNNN',
        'examples': ['3401'],
        'extract': _extract_gulf_coast_containers
    },
    'Amwaste': {
        'has_account': True,
        'format': 'NNNNNN',
        'examples': ['095565', '123776'],
        'extract': _extract_amwaste
    },
    'Lexington Site Services': {
        'has_account': True,
        'format': 'NNNNNNNNN',
        'examples': ['220009602', '218757601'],
        'extract': _extract_lexington_site_services
    },
    'Gateway Disposal': {
        'has_account': True,
        'format': 'NNNNNN',
        'examples': ['718227', '777815'],
        'extract': _extract_gateway_disposal
    },
    
    # Batch 4
    'TK Trash': {
        'has_account': True,
        'format': 'NN-NNNNNN N',
        'examples': ['75-602470 5', '75-606004 8'],
        'extract': _extract_tk_trash
    },
    'Recology': {
        'has_account': True,
        'format': 'ANNNNNNNNNNN or NNNNNNNNNN',
        'examples': ['A0040314948', '1070055251'],
        'extract': _extract_recology
    },
    'J&K Trash': {
        'has_account': True,
        'format': 'NNNNNN',
        'examples': ['585055', '585077'],
        'extract': _extract_jk_trash
    },
    'Clean Slate': {
        'has_account': True,
        'format': 'NNNNN',
        'examples': ['10335'],
        'extract': _extract_clean_slate
    },
    'Olympic Compactor Rentals': {
        'has_account': True,
        'format': 'NN-NNNNNNN',
        'examples': ['01-0080240', '01-0002543'],
        'extract': _extract_olympic_compactor_rentals
    },
    'Walker Lake Disposal': {
        'has_account': True,
        'format': 'NNN',
        'examples': ['375'],
        'extract': _extract_walker_lake_disposal
    },
    'Trident Waste': {
        'has_account': True,
        'format': 'NN-NNNNN N',
        'examples': ['01-35884 5', '01-29316 6'],
        'extract': _extract_trident_waste
    },
    'Blue Hills Environmental': {
        'has_account': True,
        'format': 'NNNNNN',
        'examples': ['112837', '112832'],
        'extract': _extract_blue_hills_environmental
    },
    'Ohio Valley Waste': {
        'has_account': True,
        'format': 'NN NNNNNNN N',
        'examples': ['90 0005041 0'],
        'extract': _extract_ohio_valley_waste
    },
    'City Waste': {
        'has_account': True,
        'format': 'NN-NNNN N',
        'examples': ['10-5648 0', '10-5909 6'],
        'extract': _extract_city_waste
    },
    
    # Batch 5
    'Vogel Disposal': {
        'has_account': True,
        'format': 'NN NNNNNNN N',
        'examples': ['02 0026280 6'],
        'extract': _extract_vogel_disposal
    },
    'WillScot': {
        'has_account': True,
        'format': 'NNNNNNNN',
        'examples': ['10464335'],
        'extract': _extract_willscot
    },
    
    # Invoice-based vendors (no account numbers)
    'Becker360': {
        'has_account': False,
        'format': None,
        'examples': [],
        'extract': lambda x: None,
        'notes': 'Invoice-based identification only'
    },
    'Pete & Pete': {
        'has_account': False,
        'format': None,
        'examples': [],
        'extract': lambda x: None,
        'notes': 'Ticket-based identification only'
    },
    'Conigliaro': {
        'has_account': False,
        'format': None,
        'examples': [],
        'extract': lambda x: None,
        'notes': 'Invoice-based identification only'
    },
    'D Crescio Trucking': {
        'has_account': False,
        'format': None,
        'examples': [],
        'extract': lambda x: None,
        'notes': 'Customer ID is name-based (WASTEOLOGY)'
    },
    'Community Disposal': {
        'has_account': False,
        'format': None,
        'examples': [],
        'extract': lambda x: None,
        'notes': 'Invoice-based identification only'
    },
    'Specialty Pallet': {
        'has_account': False,
        'format': None,
        'examples': [],
        'extract': lambda x: None,
        'notes': 'Invoice-based, uses PO numbers'
    },
    'Premier Waste': {
        'has_account': False,
        'format': None,
        'examples': [],
        'extract': lambda x: None,
        'notes': 'Invoice-based identification only'
    },
    'NK Waste': {
        'has_account': False,
        'format': None,
        'examples': [],
        'extract': lambda x: None,
        'notes': 'Uses TrashBilling ID system, multiple formats'
    },
}


# ============================================================
# TESTING FUNCTION
# ============================================================

def test_new_vendors():
    """Test all new vendor extraction functions with sample data."""
    test_cases = {
        'City of Meridian': 'Account: 99011222-01\nBilling Date: 11/05/2025',
        'Blue Diamond Disposal': 'CUSTOMER NO.\n30239\nSITE.',
        'Valley Vista': 'Account Number\nVV-478887 7\nPage',
        'SSW Frontload': 'Acct# 6215\n67250 INDUSTRY LANE',
        'JLT Trucking': 'ACCOUNT #\n1001434\nDATE',
        'Honolulu Disposal': 'ACCOUNT\n2131885000\nDATE',
        'Pelican Waste': 'Customer No. 031803\nInvoice Date',
        'Great Waste': 'Account Number\n1129190\n10/31/25',
        'WG Waste': 'ACCOUNT#\n203287\nPhone',
        'City of Boise': 'Account #: 057576800095407\nService Address',
        'Amwaste': 'ACCOUNT #: 095565\nSITE #: 0000',
        'Recology': 'ACCOUNT NO A0040314948\nBALANCE FORWARD',
        'WillScot': 'Customer #\n10464335\nBill to #',
    }
    
    print("Testing New Vendor Extraction Functions")
    print("=" * 60)
    
    for vendor, test_text in test_cases.items():
        if vendor in NEW_VENDOR_ACCOUNTS:
            config = NEW_VENDOR_ACCOUNTS[vendor]
            if config['has_account']:
                result = config['extract'](test_text)
                status = "✓" if result else "✗"
                print(f"{status} {vendor}: {result}")
            else:
                print(f"- {vendor}: No account (invoice-based)")
    
    print("\n" + "=" * 60)
    print(f"Total new vendors configured: {len(NEW_VENDOR_ACCOUNTS)}")
    with_accounts = sum(1 for v in NEW_VENDOR_ACCOUNTS.values() if v['has_account'])
    print(f"  - With account numbers: {with_accounts}")
    print(f"  - Invoice-based: {len(NEW_VENDOR_ACCOUNTS) - with_accounts}")


if __name__ == '__main__':
    test_new_vendors()
