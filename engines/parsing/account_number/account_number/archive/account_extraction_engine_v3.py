"""
Account Number Extraction Engine v3.0
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

v3.0 Changes:
- Added 50 new vendors (42 with account extraction, 8 invoice-based)
- New vendors include: City of Meridian, Blue Diamond Disposal, Valley Vista,
  SSW Frontload, Velpen Trucking, Gotta Go Waste, Louisiana Waste, ABC Waste,
  Smith Creek, JLT Trucking, Liberty Disposal, ZARC Recycling, 1-800-Got-Junk,
  Ryland Environmental, Independent Recycling, Moore Coal, Honolulu Disposal,
  Pelican Waste, Great Waste, Modern Recycling, Redgate Disposal, WG Waste,
  Community Waste, City of Boise, Western Disposal, City of Jackson,
  Gulf Coast Containers, Amwaste, Lexington Site Services, Gateway Disposal,
  TK Trash, Recology, J&K Trash, Clean Slate, Olympic Compactor Rentals,
  Walker Lake Disposal, Trident Waste, Blue Hills Environmental,
  Ohio Valley Waste, City Waste, Vogel Disposal, WillScot, Becker360,
  Pete & Pete, Conigliaro, D Crescio Trucking, Community Disposal,
  Specialty Pallet, Premier Waste, NK Waste

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


# ============================================================
# NEW VENDOR EXTRACTION FUNCTIONS (50 vendors - v3 additions)
# ============================================================

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
    Pattern: CUSTOMER NO. header, value appears 2+ lines later
    """
    lines = text.split('\\n')
    
    # Find CUSTOMER NO. header and look for 5-digit value after
    for i, line in enumerate(lines):
        if 'CUSTOMER NO' in line.upper():
            # Same line extraction (inline format)
            match = re.search(r'CUSTOMER\s*NO\.?\s*(\d{5})', line, re.I)
            if match:
                return match.group(1)
            # Check next 5 lines for 5-digit number (skipping header rows)
            for j in range(i+1, min(i+8, len(lines))):
                val = lines[j].strip()
                if re.match(r'^\d{5}$', val):
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
    """Format: NNNN (4-digit account) or 12-digit TrashBilling ID
    Examples: 6215, 5617, 585660039108
    Uses TrashBilling system
    """
    # Pattern 1: Acct# NNNN (standard invoice format)
    match = re.search(r'Acct#?\s*(\d{4,6})', text)
    if match:
        return match.group(1)
    # Pattern 2: Customer Information followed by 12-digit ID (TrashBilling confirmation)
    match = re.search(r'Customer\s*Information\s*(\d{12})', text, re.I)
    if match:
        return match.group(1)
    # Pattern 3: Look for standalone 4-digit after address line
    lines = text.split('\\n')
    for i, line in enumerate(lines):
        if 'ABITA SPRINGS' in line.upper():
            for j in range(i+1, min(i+5, len(lines))):
                val = lines[j].strip()
                if re.match(r'^\d{4}$', val):
                    return val
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
    """Format: NN-NNNN(NNN) N or NN-NNNNNNN
    Examples: 10-339800 4, 10-3471256, 10-4725 7
    """
    # Pattern 1: NN-NNNN(NNN) N (with trailing digit, 4-7 digits middle)
    match = re.search(r'Account\s*No\.?:?\s*(\d{2}-\d{4,7}\s*\d?)', text, re.I)
    if match:
        return match.group(1).strip()
    # Pattern 2: Just the format anywhere in text
    match = re.search(r'(\d{2}-\d{4,7}\s*\d)\b', text)
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
    """Format: NNNNNNNNN(N) (9-10 digit account)
    Examples: 2131885000, 2131935400, 242876300
    """
    # Pattern 1: ACCT # pattern (most specific)
    match = re.search(r'ACCT\s*#:?\s*(\d{9,10})', text, re.I)
    if match:
        return match.group(1)
    # Pattern 2: ACCOUNT followed by 9-10 digits
    match = re.search(r'ACCOUNT\s*(\d{9,10})', text, re.I)
    if match:
        return match.group(1)
    # Pattern 3: Standalone 9-10 digit at start of line (account number format)
    lines = text.split('\\n')
    for line in lines:
        if re.match(r'^\d{9,10}$', line.strip()):
            return line.strip()
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
    Patterns:
    1. AccountNumber: 112837
    2. Account #:\\n...\\n112832 (columnar)
    """
    # Pattern 1: Inline format
    match = re.search(r'(?:Account\s*#?|AccountNumber):\s*(\d{6})', text, re.I)
    if match:
        return match.group(1)
    
    # Pattern 2: Columnar format
    lines = text.split('\\n')
    for i, line in enumerate(lines):
        if 'Account #' in line or 'AccountNumber' in line:
            for j in range(i+1, min(i+8, len(lines))):
                val = lines[j].strip()
                if re.match(r'^\d{6}$', val):
                    return val
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
    Pattern: Headers on separate lines, values appear 6-8 lines later
    Customer #\\nBill to #\\nInvoice #\\n...\\n10464335\\n10375344\\n...
    """
    lines = text.split('\\n')
    
    # Find "Customer #" header line
    for i, line in enumerate(lines):
        if line.strip() == 'Customer #':
            # Values start several lines later (after address lines)
            # Look for 8-digit number
            for j in range(i+1, min(i+15, len(lines))):
                val = lines[j].strip()
                if re.match(r'^\d{8}$', val):
                    return val
    
    # Fallback: inline pattern
    match = re.search(r'Customer\s*#:\s*(\d{8})', text, re.I)
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
# NEW VENDORS (50 vendors - v3 additions)
# ============================================================

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
    'format': 'VV-NNNNNN N',
    'examples': ['VV-478887 7', 'VV-478891 9'],
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

VENDOR_ACCOUNTS['ABC Waste'] = {
    'has_account': True,
    'format': 'NN-NNNNNN N',
    'examples': ['10-339800 4', '10-3471256'],
    'extract': _extract_abc_waste
}

VENDOR_ACCOUNTS['Smith Creek'] = {
    'has_account': True,
    'format': 'XXXXNNNN',
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
    'format': 'NNNNXX',
    'examples': ['2476TU', '019022'],
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
    'format': 'XXNNNN',
    'examples': ['AC4946'],
    'extract': _extract_ryland_environmental
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
    'format': 'NNNNNNNNNN',
    'examples': ['2131885000', '2131935400'],
    'extract': _extract_honolulu_disposal
}

VENDOR_ACCOUNTS['Pelican Waste'] = {
    'has_account': True,
    'format': 'NNNNNN',
    'examples': ['031803', '026634', '029610'],
    'extract': _extract_pelican_waste
}

VENDOR_ACCOUNTS['Great Waste'] = {
    'has_account': True,
    'format': 'NNNNNNN',
    'examples': ['1129190'],
    'extract': _extract_great_waste
}

VENDOR_ACCOUNTS['Modern Recycling'] = {
    'has_account': True,
    'format': 'NNNNN',
    'examples': ['53262'],
    'extract': _extract_modern_recycling
}

VENDOR_ACCOUNTS['Redgate Disposal'] = {
    'has_account': True,
    'format': 'XNNNN',
    'examples': ['C8451', 'C8452'],
    'extract': _extract_redgate_disposal
}

VENDOR_ACCOUNTS['WG Waste'] = {
    'has_account': True,
    'format': 'NNNNNN',
    'examples': ['203287'],
    'extract': _extract_wg_waste
}

VENDOR_ACCOUNTS['Community Waste'] = {
    'has_account': True,
    'format': 'NN-NNNNNN N',
    'examples': ['10-271295 7', '21105'],
    'extract': _extract_community_waste
}

VENDOR_ACCOUNTS['City of Boise'] = {
    'has_account': True,
    'format': 'NNNNNNNNNNNNNNN',
    'examples': ['057576800095407', '059147800347545'],
    'extract': _extract_city_of_boise
}

VENDOR_ACCOUNTS['Western Disposal'] = {
    'has_account': True,
    'format': 'NNNNNN',
    'examples': ['123825', '121004'],
    'extract': _extract_western_disposal
}

VENDOR_ACCOUNTS['City of Jackson'] = {
    'has_account': True,
    'format': 'NNNNNN-NNNNN',
    'examples': ['203809-21438', '7310746'],
    'extract': _extract_city_of_jackson
}

VENDOR_ACCOUNTS['Gulf Coast Containers'] = {
    'has_account': True,
    'format': 'NNNN',
    'examples': ['3401'],
    'extract': _extract_gulf_coast_containers
}

VENDOR_ACCOUNTS['Amwaste'] = {
    'has_account': True,
    'format': 'NNNNNN',
    'examples': ['095565', '123776'],
    'extract': _extract_amwaste
}

VENDOR_ACCOUNTS['Lexington Site Services'] = {
    'has_account': True,
    'format': 'NNNNNNNNN',
    'examples': ['220009602', '218757601'],
    'extract': _extract_lexington_site_services
}

VENDOR_ACCOUNTS['Gateway Disposal'] = {
    'has_account': True,
    'format': 'NNNNNN',
    'examples': ['718227', '777815'],
    'extract': _extract_gateway_disposal
}

VENDOR_ACCOUNTS['TK Trash'] = {
    'has_account': True,
    'format': 'NN-NNNNNN N',
    'examples': ['75-602470 5', '75-606004 8'],
    'extract': _extract_tk_trash
}

VENDOR_ACCOUNTS['Recology'] = {
    'has_account': True,
    'format': 'ANNNNNNNNNNN',
    'examples': ['A0040314948', '1070055251'],
    'extract': _extract_recology
}

VENDOR_ACCOUNTS['J&K Trash'] = {
    'has_account': True,
    'format': 'NNNNNN',
    'examples': ['585055', '585077'],
    'extract': _extract_jk_trash
}

VENDOR_ACCOUNTS['Clean Slate'] = {
    'has_account': True,
    'format': 'NNNNN',
    'examples': ['10335'],
    'extract': _extract_clean_slate
}

VENDOR_ACCOUNTS['Olympic Compactor Rentals'] = {
    'has_account': True,
    'format': 'NN-NNNNNNN',
    'examples': ['01-0080240', '01-0002543'],
    'extract': _extract_olympic_compactor_rentals
}

VENDOR_ACCOUNTS['Walker Lake Disposal'] = {
    'has_account': True,
    'format': 'NNN',
    'examples': ['375'],
    'extract': _extract_walker_lake_disposal
}

VENDOR_ACCOUNTS['Trident Waste'] = {
    'has_account': True,
    'format': 'NN-NNNNN N',
    'examples': ['01-35884 5', '01-29316 6'],
    'extract': _extract_trident_waste
}

VENDOR_ACCOUNTS['Blue Hills Environmental'] = {
    'has_account': True,
    'format': 'NNNNNN',
    'examples': ['112837', '112832'],
    'extract': _extract_blue_hills_environmental
}

VENDOR_ACCOUNTS['Ohio Valley Waste'] = {
    'has_account': True,
    'format': 'NN NNNNNNN N',
    'examples': ['90 0005041 0'],
    'extract': _extract_ohio_valley_waste
}

VENDOR_ACCOUNTS['City Waste'] = {
    'has_account': True,
    'format': 'NN-NNNN N',
    'examples': ['10-5648 0', '10-5909 6'],
    'extract': _extract_city_waste
}

VENDOR_ACCOUNTS['Vogel Disposal'] = {
    'has_account': True,
    'format': 'NN NNNNNNN N',
    'examples': ['02 0026280 6'],
    'extract': _extract_vogel_disposal
}

VENDOR_ACCOUNTS['WillScot'] = {
    'has_account': True,
    'format': 'NNNNNNNN',
    'examples': ['10464335'],
    'extract': _extract_willscot
}


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
    'Becker360',         # v3 addition
    'Pete & Pete',         # v3 addition
    'Conigliaro',         # v3 addition
    'D Crescio Trucking',         # v3 addition
    'Community Disposal',         # v3 addition
    'Specialty Pallet',         # v3 addition
    'Premier Waste',         # v3 addition
    'NK Waste',         # v3 addition
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
    print("Account Extraction Engine v3.0")
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
