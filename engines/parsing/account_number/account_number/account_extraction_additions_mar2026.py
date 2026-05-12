"""
Account Extraction Additions - March 2026
Patterns for ops_database invoice processing pipeline.

8 new vendors + 6 pattern fixes for literal \\n text format.

v9.2 additions (2026-03-10):
- Fixed 9 extraction patterns for two-column OCR layouts (label/value on separate lines)
- Added 4 new vendor patterns (Key Works, RICHGROVE REFUSE, Doll's Disposal, PULASKI COUNTY)
- Added 5 NO_ACCOUNT entries (WG Waste, Dumpster Pros, Fix It Right, McNeilly Wood, Atlantic Recycling)

v9.3 additions (2026-03-11):
- 10 new vendor extraction patterns from bill image review
  (Waste Pro v2, Meridian Waste, Ace Recycling, GFL, Solid Waste Authority v2,
   Casella v2, Best Way Disposal, FCC Environmental, Robinson Waste v2,
   City of North Las Vegas)
- 6 NO_ACCOUNT entries (American Disposal Systems, Wise Environmental,
  ACES Disposal, Community Disposal, Hamilton Alliance, Priority Waste)
- 1 NO_ACCOUNT entry (Western Waste Services)
"""
import re
from typing import Optional


# ============================================================
# NEW VENDOR EXTRACTION FUNCTIONS
# ============================================================

def _extract_derby_city(text: str) -> Optional[str]:
    """Format: Customer ID followed by letter + digits (C1504)
    Example: C1504
    """
    match = re.search(r'Customer ID[:\s]*(?:\\n|\s)*([A-Z]\d{3,5})', text, re.I)
    return match.group(1).upper() if match else None


def _extract_chisms_trash(text: str) -> Optional[str]:
    """Format: Acct#: NNNN or Acct# NNNN
    Example: 9553
    """
    match = re.search(r'Acct#:?\s*(\d{4,6})', text, re.I)
    return match.group(1) if match else None


def _extract_woody_sons(text: str) -> Optional[str]:
    """Format: Customer Number: NNNNN
    Example: 10744
    Layout: table-style — labels listed first, values follow on later lines.
    """
    normalized = text.replace('\\n', '\n')
    lines = normalized.split('\n')
    for i, line in enumerate(lines):
        if 'Customer Number' in line:
            for j in range(i + 1, min(i + 6, len(lines))):
                val = lines[j].strip()
                if re.match(r'^\d{4,6}$', val):
                    return val
    return None


def _extract_craven_ag(text: str) -> Optional[str]:
    """Format: Customer ID: letter + digits (G528)
    Example: G528
    """
    match = re.search(r'Customer ID:?\s*(?:\\n|\s)*([A-Z]\d{3,5})', text, re.I)
    return match.group(1).upper() if match else None


def _extract_royal_sanitation(text: str) -> Optional[str]:
    """Format: Account #: NNNN or 'account number NNNN'
    Example: 5295
    Layout: table-style — labels listed first, values follow on later lines.
    """
    # Inline format: 'account number 5295'
    match = re.search(r'account\s*number\s+(\d{4,6})', text, re.I)
    if match:
        return match.group(1)
    # Table format: Account #: label with value on later line
    normalized = text.replace('\\n', '\n')
    lines = normalized.split('\n')
    for i, line in enumerate(lines):
        if re.search(r'Account\s*#', line, re.I):
            for j in range(i + 1, min(i + 6, len(lines))):
                val = lines[j].strip()
                if re.match(r'^\d{4,6}$', val):
                    return val
    return None


def _extract_tri_state_waste(text: str) -> Optional[str]:
    """Format: 6-digit customer number near CUSTOMER label
    Example: 196871
    Layout: values appear before labels in OCR (table header format)
    """
    normalized = text.replace('\\n', '\n')
    lines = normalized.split('\n')
    for i, line in enumerate(lines):
        if line.strip().upper() == 'CUSTOMER' or 'CUSTOMER' in line.upper().split('\t'):
            # Value is typically 1-3 lines before the label
            for j in range(max(0, i - 3), i):
                val = lines[j].strip()
                if re.match(r'^\d{5,7}$', val):
                    return val
    return None


def _extract_a1_waste(text: str) -> Optional[str]:
    """Format: Account Id: XX-NNNN-NNNN
    Example: WA-2501-6674
    """
    match = re.search(r'Account\s*Id:\s*([A-Z]{2}-\d{4}-\d{4})', text, re.I)
    return match.group(1).upper() if match else None


# ============================================================
# CORRECTED VENDOR EXTRACTION FUNCTIONS
# ============================================================

def _extract_pueblo_of_zuni(text: str) -> Optional[str]:
    """Format: Customer # Z-NN (letter-dash-digits)
    Example: Z-10
    """
    match = re.search(r'Customer\s*#\s*([A-Z]\s*-\s*\d{1,4})', text, re.I)
    if match:
        return match.group(1).replace(' ', '').upper()
    return None


def _extract_organix_recycling(text: str) -> Optional[str]:
    """Format: Customer Number: NNNNNNNNN (9 digits)
    Example: 599124169
    """
    match = re.search(r'Customer Number:?\s*(?:\\n|\s)*(\d{7,10})', text, re.I)
    return match.group(1) if match else None


def _extract_panzarella_waste(text: str) -> Optional[str]:
    """Format: Account No. NN-NNNN N
    Example: 01-4649 9
    """
    match = re.search(r'Account\s*No\.?\s*(\d{2}-\d{4}\s*\d)', text, re.I)
    return match.group(1) if match else None


# ============================================================
# PATTERN FIXES — handle literal \\n text format from BigQuery
# ============================================================

def _extract_crr_fixed(text: str) -> Optional[str]:
    """Format: NN-NNNNNNNNN (2 digits, dash, 8 digits)
    Examples: 93-00312437, 01-0001038
    FIX: Original pattern missed dash format, grabbed invoice# instead.
    """
    lines = text.split('\\n')
    for i, line in enumerate(lines):
        if 'Account Number' in line:
            for j in range(i + 1, min(i + 10, len(lines))):
                val = lines[j].strip()
                # Prefer dash format (actual account)
                if re.match(r'^\d{2}-\d{7,10}(-\d)?$', val):
                    return val
                # Also accept plain 9-digit (original format)
                if re.match(r'^[A-Z]?\d{8,10}$', val):
                    return val
    return None

def _extract_edco_disposal_fixed(text: str) -> Optional[str]:
    """Format: NN-XX NNNNNN (letters AND/OR digits in position 2)
    Examples: 55-J5 729042, 37-U5 730295, 25-3R 120075
    FIX: Feb2026 pattern used [A-Z]{2} which missed digit+letter combos.
    """
    match = re.search(r'(\d{2}-[A-Z0-9]{2}\s*\d{6})', text)
    return match.group(1) if match else None


def _extract_robinson_waste_fixed(text: str) -> Optional[str]:
    """Format: NNNNN.NNN, NNNNN-NNN, or simple 4-5 digit
    Examples: 55779.64, 51001, 2090, 1501
    FIX: Normalize literal \\n; only look BEFORE the label (values precede labels
    in Robinson header). After the label is the street address — never match that.
    """
    if 'CUSTOMER ISSUE TICKET' in text.upper():
        return None

    normalized = text.replace('\\n', '\n')
    lines = normalized.split('\n')

    # Format 1: NNNNN.NNN or NNNNN-NNN (dotted/dashed account)
    for line in lines[:25]:
        match = re.search(r'\b(\d{5}[\.\-]\d{1,3})\b', line)
        if match:
            return match.group(1)

    # Format 2: ACCOUNT NO. label — value is always BEFORE the label
    for i, line in enumerate(lines[:20]):
        if 'ACCOUNT NO' in line.upper():
            # Check same line first (inline format)
            match = re.search(r'ACCOUNT\s*NO\.?\s+(\d{4,5})\b', line, re.I)
            if match:
                return match.group(1)
            # Otherwise look backwards (header table format)
            for j in range(i - 1, max(0, i - 6) - 1, -1):
                val = lines[j].strip()
                if re.match(r'^\d{4,5}$', val):
                    return val

    return None


def _extract_standard_waste_fixed(text: str) -> Optional[str]:
    """Format: Account ID or Customer ID — multiple formats.
    Formats:
      1. UPS.NJEDI1, UPS-NJBAY — dot/dash separator
      2. WESCO7802R, WESCO1088P — alphanumeric, no separator
      3. UHG #213 — alpha + # + digits
    FIX v2: Broaden to accept any alphanumeric code after Account/Customer ID label.
    """
    normalized = text.replace('\\n', '\n')

    # Format 1: Inline — Account/Customer ID followed by alphanumeric code
    # Matches: UPS.NJEDI1, UPS-NJBAY, WESCO7802R, UHG #213
    m = re.search(r'(?:Account|Customer)\s*ID[\s:]*([A-Z][A-Z0-9#\.\-\s]{2,14})', normalized, re.I)
    if m:
        val = m.group(1).strip()
        # Stop at common next-field labels
        val = re.split(r'\s+(?:Invoice|Date|Amount|Page|Due|Service)', val, flags=re.I)[0].strip()
        if len(val) >= 3:
            return val.upper()

    # Format 2: Multi-line — label on one line, value 1-5 lines later (skip weekday+date)
    lines = normalized.split('\n')
    for i, line in enumerate(lines):
        if re.search(r'(?:Account|Customer)\s*ID', line, re.I):
            for j in range(i + 1, min(i + 6, len(lines))):
                val = lines[j].strip()
                # Skip weekday names and dates
                if re.match(r'^(Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday)$', val, re.I):
                    continue
                if re.match(r'^\d{1,2}/\d{1,2}/\d{2,4}$', val):
                    continue
                # Accept alphanumeric codes (3+ chars starting with letter)
                if re.match(r'^[A-Z][A-Z0-9#\.\-]{2,14}$', val, re.I):
                    return val.upper()

    return None


def _extract_modern_recycling_fixed(text: str) -> Optional[str]:
    """Format: Customer Number: NNNNN (4-6 digit, standalone)
    Examples: 53262, 4179, 68741
    FIX: Normalize \\n; search several lines after label for standalone digits.
    Skip service number format (NNNNNN-NNNN).
    """
    normalized = text.replace('\\n', '\n')
    lines = normalized.split('\n')
    for i, line in enumerate(lines):
        if 'Customer Number' in line:
            # Same line: Customer Number: 53262
            match = re.search(r'Customer Number:?\s+(\d{4,6})$', line, re.I)
            if match:
                return match.group(1)
            # Search next few lines for standalone digit value
            for j in range(i + 1, min(i + 4, len(lines))):
                val = lines[j].strip()
                if re.match(r'^\d{4,6}$', val):
                    return val
    return None


def _extract_tower_compactor_fixed(text: str) -> Optional[str]:
    """Format: Alphanumeric Customer ID (UPS012, QED001, WASOOR)
    Examples: UPS012, QED001, WASOOR
    FIX: Accept all-letter IDs (3-8 alphanumeric chars).
    """
    normalized = text.replace('\\n', '\n')
    lines = normalized.split('\n')
    for i, line in enumerate(lines):
        if 'Customer ID' in line:
            if i + 1 < len(lines):
                val = lines[i + 1].strip()
                if re.match(r'^[A-Z][A-Z0-9]{2,7}$', val, re.I):
                    return val.upper()
    return None


def _extract_jamaica_ash_fixed2(text: str) -> Optional[str]:
    """Format: ACCOUNT# NNNNNN
    Example: 482277
    FIX: Handle literal \\n between label and value.
    """
    match = re.search(r'ACCOUNT#\s*(?:\\n|\s)*(\d{5,7})', text, re.I)
    return match.group(1) if match else None


# ============================================================
# v9.2 EXTRACTION PATTERN FIXES (2026-03-10 — Gap 6)
# Root cause: two-column OCR layouts where labels/values are
# on separate lines separated by literal \n in BigQuery text.
# ============================================================

def _extract_jp_mascaro_fixed(text: str) -> Optional[str]:
    """JP Mascaro — two invoice formats:
    - Berks County: labeled CUSTOMER NO. header, 5-6 digit values (88395, 89083)
    - Souderton: positional (no label), 6 digit values (187877, 188377)
    FIX: Original required exactly 6 digits; Berks uses 5. Also handle
    Souderton positional format where customer# is standalone 5-6 digit
    number after the date line.
    """
    normalized = text.replace('\\n', '\n')
    lines = normalized.split('\n')

    # Format 1: CUSTOMER NO. label — value is 5-6 digits nearby
    for i, line in enumerate(lines):
        if 'CUSTOMER NO' in line.upper():
            for j in range(max(0, i - 3), min(i + 12, len(lines))):
                val = lines[j].strip()
                if re.match(r'^\d{5,6}$', val):
                    return val

    # Format 2: Souderton positional — standalone 5-6 digit number after
    # date pattern (e.g. Feb-12-2026), before billing address.
    # Header layout: ...invoice#(10d)/Page/Date/CUSTOMER#(5-6d)/BillTo...
    for i, line in enumerate(lines[:15]):
        # Look for date-like line
        if re.match(r'^[A-Z][a-z]{2}-\d{2}-\d{4}$', line.strip()):
            # Customer number is the next standalone 5-6 digit number
            for j in range(i + 1, min(i + 3, len(lines))):
                val = lines[j].strip()
                if re.match(r'^\d{5,6}$', val):
                    return val

    # Format 3: Inline "CUSTOMER NO" then value on same line
    match = re.search(r'CUSTOMER\s*NO\.?\s*(\d{5,6})', normalized, re.I)
    if match:
        return match.group(1)

    # Format 4: Remittance section — value before "CUSTOMER NO." label
    match = re.search(r'(\d{5,6})\s*\n\s*INVOICE\s*DATE\s*\n\s*CUSTOMER\s*NO',
                       normalized, re.I)
    if match:
        return match.group(1)

    return None


def _extract_friedman_recycling_fixed(text: str) -> Optional[str]:
    """Friedman Recycling — two-column layout with variable column order.
    Account number is 7-8 digits near "FRIEDMAN" (before OR after) and
    before "Account Number" label.
    FIX: Original used hard-coded line index 5. Now searches contextually
    while keeping line-5 as primary (works for majority of invoices).
    """
    normalized = text.replace('\\n', '\n')
    lines = normalized.split('\n')

    # Pattern 1: Original positional (line 5) — works for most invoices
    if len(lines) > 5:
        val = lines[5].strip()
        if re.match(r'^\d{7,8}$', val):
            return val

    # Pattern 2: Number near "FRIEDMAN" (before OR after, within 3 lines)
    for i, line in enumerate(lines):
        if 'FRIEDMAN' in line.upper():
            # Check lines before and after
            for j in range(max(0, i - 3), min(i + 4, len(lines))):
                if j == i:
                    continue
                val = lines[j].strip()
                if re.match(r'^\d{7,8}$', val):
                    return val

    # Pattern 3: Number before "Account Number" label
    for i, line in enumerate(lines):
        if 'Account Number' in line:
            for j in range(max(0, i - 6), i):
                val = lines[j].strip()
                if re.match(r'^\d{7,8}$', val):
                    return val

    # Pattern 4: Inline
    match = re.search(r'Account\s*Number[:\s]*(\d{7,8})', normalized, re.I)
    if match:
        return match.group(1)

    return None


def _extract_rumpke_fixed2(text: str) -> Optional[str]:
    """Rumpke — Customer #: on one line, value on next (with Access Code in between).
    FIX: Feb2026 fix used inline regex that didn't match across literal \\n lines.
    """
    normalized = text.replace('\\n', '\n')

    # Inline: Customer # 0201169794 or Account # 0201169794
    match = re.search(r'(?:Account|Customer|Cust)\s*#:?\s*(\d{10})', normalized, re.I)
    if match:
        return match.group(1)

    # Multi-line: label on one line, value within next 4 lines
    lines = normalized.split('\n')
    for i, line in enumerate(lines):
        if re.search(r'(?:Account|Customer|Cust)\s*(?:#|Number)', line, re.I):
            for j in range(i + 1, min(i + 5, len(lines))):
                val = lines[j].strip()
                if re.match(r'^\d{10}$', val):
                    return val

    # Remittance section: CUSTOMER NUMBER then 10-digit
    match = re.search(r'CUSTOMER\s*NUMBER\s*\n\s*(\d{10})', normalized, re.I)
    if match:
        return match.group(1)

    return None


def _extract_stericycle_fixed(text: str) -> Optional[str]:
    """Stericycle — Shred-it branded invoices use 'Customer ID:' not
    'Customer No. (Payer)'. Two-column layout: labels grouped then values grouped.
    FIX: Add Customer ID label + two-column layout handling.
    """
    normalized = text.replace('\\n', '\n')

    # Inline format (page 2): Customer ID: 3001303944
    match = re.search(r'Customer\s*ID:?\s*(\d{10})', normalized, re.I)
    if match:
        return match.group(1)

    # Original format: Customer No. (Payer)
    match = re.search(r'Customer\s*No\.\s*\(Payer\)\s*\n\s*(\d{10})', normalized, re.I)
    if match:
        return match.group(1)

    # Two-column: labels block then values block
    lines = normalized.split('\n')
    for i, line in enumerate(lines):
        if 'Customer ID' in line or 'Customer No' in line:
            # Value is in the next block of lines (may have other labels in between)
            for j in range(i + 1, min(i + 8, len(lines))):
                val = lines[j].strip()
                if re.match(r'^\d{10}$', val):
                    return val

    return None


def _extract_capital_waste_fixed(text: str) -> Optional[str]:
    """Capital Waste — uses 'CUSTOMER NUMBER' label (not 'ACCOUNT').
    Two-column layout: labels grouped, values in adjacent block.
    FIX: Original required exact match on 'ACCOUNT'. Added CUSTOMER NUMBER.
    """
    normalized = text.replace('\\n', '\n')
    lines = normalized.split('\n')

    # Pattern 1: CUSTOMER NUMBER label — value nearby
    for i, line in enumerate(lines):
        if 'CUSTOMER NUMBER' in line.upper() or line.strip().upper() == 'ACCOUNT':
            for j in range(max(0, i - 5), min(i + 8, len(lines))):
                val = lines[j].strip()
                if re.match(r'^\d{6,8}$', val):
                    return val

    # Pattern 2: Inline
    match = re.search(r'(?:CUSTOMER\s*NUMBER|ACCOUNT)[:\s]*(\d{6,8})', normalized, re.I)
    if match:
        return match.group(1)

    return None


def _extract_casella_fixed2(text: str) -> Optional[str]:
    """Casella — multiple formats: K/KI prefix, HS-NNNNN, NN-NNNNN N.
    FIX: Normalize literal \\n before line splitting. Feb2026 fix used
    text.split('\\n') which doesn't work with literal backslash-n text.
    """
    if 'PRICE CONFIRMATION' in text.upper():
        return None
    normalized = text.replace('\\n', '\n')
    lines = normalized.split('\n')

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
            # Next lines (two-column layout)
            for j in range(i + 1, min(i + 6, len(lines))):
                val = lines[j].strip()
                if re.match(r'^K[IR]?\d{7,9}$', val, re.I):
                    return val.upper()
                if re.match(r'^\d{10}$', val):
                    return val
                m = re.search(r'(\d{2}-\d{5}\s*\d)', val)
                if m:
                    return m.group(1).strip()
                # HS-NNNNN format
                m = re.match(r'^[A-Z]{2}-\d{4,6}$', val, re.I)
                if m:
                    return val.strip()
    return None


def _extract_zarc_recycling_fixed(text: str) -> Optional[str]:
    """ZARC Recycling — Customer ID: inline.
    FIX: Original required exactly 3 digits but account 1147 is 4 digits.
    """
    match = re.search(r'Customer\s*ID:?\s*(\d{3,5})', text, re.I)
    if match:
        return match.group(1)
    normalized = text.replace('\\n', '\n')
    match = re.search(r'Customer\s*ID:?\s*(\d{3,5})', normalized, re.I)
    return match.group(1) if match else None


def _extract_nk_waste_fixed(text: str) -> Optional[str]:
    """NK Waste — multiple sub-vendors with different formats:
    - Hensley: Account #: 780 (3-digit)
    - TrashBilling vendors: ID#: 123990032003 (12-digit)
    - Swatco: ACCOUNT NO 5-digit (original pattern)
    FIX: Handle variable digit lengths and ID# format.
    """
    normalized = text.replace('\\n', '\n')

    # Format 1: Account #: NNN (short accounts)
    match = re.search(r'Account\s*#:?\s*(\d{3,6})', normalized, re.I)
    if match:
        return match.group(1)

    # Format 2: Acct# NNN (inline)
    match = re.search(r'Acct\s*#:?\s*(\d{3,6})', normalized, re.I)
    if match:
        return match.group(1)

    # Format 3: ID#: NNNNNNNNNNNN (TrashBilling 12-digit)
    match = re.search(r'ID\s*#:?\s*(\d{9,15})', normalized, re.I)
    if match:
        return match.group(1)

    # Format 4: ACCOUNT NO header with value nearby (5-digit, original)
    lines = normalized.split('\n')
    for i, line in enumerate(lines):
        if 'ACCOUNT NO' in line.upper() and 'NAME' not in line.upper():
            for j in range(i + 1, min(i + 6, len(lines))):
                val = lines[j].strip()
                if re.match(r'^\d{3,6}$', val):
                    return val

    return None


def _extract_waste_pro_fixed(text: str) -> Optional[str]:
    """Waste Pro — multiple label formats:
    1. Account Number: NNNNNN (inline or two-column)
    2. Account #/ Invoice#: NNNNNN/NNNNNNNNNN (slash-separated)
    3. Account # Invoice#: NNNNNN/NNNNNNNNNN
    FIX: Feb2026 fix only handled inline. Added slash format + two-column.
    """
    normalized = text.replace('\\n', '\n')

    # Format 1: Slash-separated (Account #/ Invoice#:\n{acct}/{inv})
    match = re.search(r'Account\s*#/?.*Invoice.*?:?\s*\n?\s*(\d{4,7})\s*/\s*\d+', normalized, re.I)
    if match:
        return match.group(1)

    # Format 2: Inline Account Number: NNNNNN
    match = re.search(r'Account\s*Number:?\s*(\d{4,7})', normalized, re.I)
    if match:
        return match.group(1)

    # Format 3: Two-column — Account Number label then value in later lines
    lines = normalized.split('\n')
    for i, line in enumerate(lines):
        if re.search(r'Account\s*Number', line, re.I):
            for j in range(i + 1, min(i + 10, len(lines))):
                val = lines[j].strip()
                if re.match(r'^\d{4,7}$', val):
                    return val
                # Slash-separated on value line
                match = re.match(r'^(\d{4,7})/\d+$', val)
                if match:
                    return match.group(1)

    return None


def _extract_advance_disposal_fixed(text: str) -> Optional[str]:
    """Advance Disposal — uses CUSTOMER NO. label with two-column layout.
    Values appear several lines after labels (CUSTOMER NO./INVOICE DATE/etc).
    FIX: Handle CUSTOMER NO. label + multi-line offset.
    """
    normalized = text.replace('\\n', '\n')
    lines = normalized.split('\n')

    # Pattern 1: CUSTOMER NO. label — value is 5-7 digits within next 8 lines
    for i, line in enumerate(lines):
        if 'CUSTOMER NO' in line.upper():
            for j in range(i + 1, min(i + 8, len(lines))):
                val = lines[j].strip()
                if re.match(r'^\d{5,7}$', val):
                    return val

    # Pattern 2: Account Number (inline or multi-line)
    match = re.search(r'Account\s*Number:?\s*(\d{5,7})', normalized, re.I)
    if match:
        return match.group(1)

    return None


def _extract_best_pick_disposal_fixed(text: str) -> Optional[str]:
    """Best Pick Disposal — uses 'Account No:' label (not '#').
    Format: Account No: 14374500 (inline, colon-separated).
    FIX: Handle 'Account No:' format in addition to 'Account #'.
    """
    normalized = text.replace('\\n', '\n')
    # Pattern 1: Account No: NNNNNNNN (inline, colon-separated)
    match = re.search(r'Account\s*No:?\s*(\d{7,9})', normalized, re.I)
    if match:
        return match.group(1)
    # Pattern 2: Account/Acct # (original format)
    match = re.search(r'(?:Account|Acct)\s*#:?\s*(\d{7,9})', normalized, re.I)
    if match:
        return match.group(1)
    # Multi-line fallback
    lines = normalized.split('\n')
    for i, line in enumerate(lines):
        if re.search(r'(?:Account|Acct)\s*(?:No|#)', line, re.I):
            for j in range(i + 1, min(i + 5, len(lines))):
                val = lines[j].strip()
                if re.match(r'^\d{7,9}$', val):
                    return val
    return None


def _extract_city_of_casper_fixed(text: str) -> Optional[str]:
    """City of Casper — uses 'Customer ID #NNNNNN' and 'Customer Number NNNNNN'.
    FIX: Handle 'Customer ID #' (hash-separated) and 'Customer Number' formats.
    Note: 'Statement ID' is NOT the account — customer number is the account.
    """
    normalized = text.replace('\\n', '\n')
    # Pattern 1: Customer Number NNNNNN (inline)
    match = re.search(r'Customer\s*Number\s*(\d{5,8})', normalized, re.I)
    if match:
        return match.group(1)
    # Pattern 2: Customer ID #NNNNNN (hash prefix)
    match = re.search(r'Customer\s*ID\s*#\s*(\d{5,8})', normalized, re.I)
    if match:
        return match.group(1)
    # Pattern 3: Account/Acct #
    match = re.search(r'(?:Account|Acct)\s*#:?\s*(\d{5,8})', normalized, re.I)
    if match:
        return match.group(1)
    return None


def _extract_jettison_environmental_fixed(text: str) -> Optional[str]:
    """Jettison Environmental — uses 'Customer:' label with account number
    inline followed by customer name (e.g. '109991 WASTEOLOGY GROUP').
    FIX: Handle 'Customer:' label with inline account number.
    """
    normalized = text.replace('\\n', '\n')
    # Pattern 1: Customer: NNNNNN CUSTOMER_NAME (inline)
    match = re.search(r'Customer:?\s*(\d{5,7})\s+\w', normalized, re.I)
    if match:
        return match.group(1)
    # Pattern 2: Account/Acct #
    match = re.search(r'(?:Account|Acct)\s*#:?\s*(\d{5,7})', normalized, re.I)
    if match:
        return match.group(1)
    # Multi-line: Customer label then value on next line
    lines = normalized.split('\n')
    for i, line in enumerate(lines):
        if re.search(r'Customer', line, re.I):
            match = re.search(r'(\d{5,7})', line)
            if match:
                return match.group(1)
            for j in range(i + 1, min(i + 3, len(lines))):
                match = re.search(r'^(\d{5,7})\b', lines[j].strip())
                if match:
                    return match.group(1)
    return None


def _extract_mark_dunning_fixed2(text: str) -> Optional[str]:
    """Mark Dunning — ACCOUNT# with literal \\n between label and value.
    FIX: Normalize \\n. Feb2026 fix handled same-line but not literal \\n multi-line.
    """
    normalized = text.replace('\\n', '\n')
    match = re.search(r'ACCOUNT#\s*(\d{5,10})', normalized, re.I)
    if match:
        return match.group(1)
    lines = normalized.split('\n')
    for i, line in enumerate(lines):
        if 'ACCOUNT#' in line.upper():
            for j in range(i + 1, min(i + 4, len(lines))):
                val = lines[j].strip()
                if re.match(r'^\d{5,10}$', val):
                    return val
    return None


def _extract_recology_fixed(text: str) -> Optional[str]:
    """Recology — Multiple formats across divisions.
    Formats:
      1. Inline: Account Number: 032644813 (7-10 digits)
      2. Multi-line: Account\\nNumber on separate lines, value below
      3. Columnar header: Invoice\\nInvoice\\nAccount\\nDate\\nNumber\\nNumber\\n
         followed by data line: 12/20/24 8551003010439 8100236641
         (3 values: date, invoice#, account#)
      4. Account No. NNNNNNNNNN
    FIX: Accept 7-10 digit accounts (not just 10). Add columnar header format.
    """
    normalized = text.replace('\\n', '\n')
    lines = normalized.split('\n')

    # Pattern 0: A-prefix + 10 digits (A1810523456) — most common failing format
    match = re.search(r'(?:Account|Customer)\s*(?:Number|No\.?)\s*:?\s*(A\d{10})', normalized, re.I)
    if match:
        return match.group(1).upper()

    # Pattern 0b: Multi-line A-prefix
    for i, line in enumerate(lines):
        if re.search(r'(?:ACCOUNT|CUSTOMER)\s*(?:NUMBER|NO)', line, re.I):
            for j in range(i + 1, min(i + 6, len(lines))):
                val = lines[j].strip()
                if re.match(r'^A\d{10}$', val, re.I):
                    return val.upper()

    # Pattern 1: Inline Account/Customer Number: NNNNNNN+
    match = re.search(r'(?:Account|Customer)\s*Number[:\s]*(\d{7,10})', normalized, re.I)
    if match:
        return match.group(1)

    # Pattern 1b: Account No. NNNNNNNNNN
    match = re.search(r'Account\s*No\.?\s*(\d{7,10})', normalized, re.I)
    if match:
        return match.group(1)

    # Pattern 1c: Customer Account: NNNNNNN
    match = re.search(r'Customer\s*Account[:\s]*(\d{6,10})', normalized, re.I)
    if match:
        return match.group(1)

    # Pattern 1d: Customer # (6-7 digits)\nNNNNNNN (King County division)
    for i, line in enumerate(lines):
        if re.search(r'Customer\s*#', line, re.I):
            for j in range(i + 1, min(i + 3, len(lines))):
                val = lines[j].strip()
                if re.match(r'^\d{6,10}$', val):
                    return val

    # Pattern 2: Two-column — "Customer" or "Account" then "Number" on separate lines
    for i, line in enumerate(lines[:-1]):
        upper = line.strip().lower()
        if upper in ('customer', 'account'):
            if i + 1 < len(lines) and lines[i + 1].strip().lower() == 'number':
                for j in range(i + 2, min(i + 8, len(lines))):
                    matches = re.findall(r'\b(\d{7,10})\b', lines[j])
                    if matches:
                        return matches[-1]  # Last match (account is after invoice#)
        # Combined on one line
        if ('customer' in upper or 'account' in upper) and 'number' in upper:
            for j in range(i + 1, min(i + 8, len(lines))):
                val = lines[j].strip()
                if re.match(r'^\d{7,10}$', val):
                    return val
                matches = re.findall(r'\b(\d{7,10})\b', val)
                if matches:
                    return matches[-1]

    # Pattern 3: Columnar header — Invoice/Invoice/Account headers followed by data line
    # OCR: Invoice\nInvoice\nAccount\nDate\nNumber\nNumber\n12/20/24 8551003010439 8100236641
    for i, line in enumerate(lines):
        if line.strip().lower() == 'account' and i >= 1:
            # Look for "Number" lines below
            num_count = 0
            for j in range(i + 1, min(i + 4, len(lines))):
                if lines[j].strip().lower() in ('number', 'date'):
                    num_count += 1
            if num_count >= 2:
                # Data line follows the header block
                for j in range(i + 1, min(i + 8, len(lines))):
                    data_line = lines[j].strip()
                    # Match: date invoice_number account_number
                    matches = re.findall(r'\b(\d{7,13})\b', data_line)
                    if len(matches) >= 2:
                        # Account is the last long number
                        return matches[-1]

    return None


# ============================================================
# v9.2 NEW VENDOR EXTRACTION FUNCTIONS (Gap 6 Action 4)
# ============================================================

def _extract_key_works(text: str) -> Optional[str]:
    """Key Works — Account Number followed by 6-digit value.
    Example: Account Number 630100
    """
    normalized = text.replace('\\n', '\n')
    match = re.search(r'Account\s*Number:?\s*(\d{5,7})', normalized, re.I)
    if match:
        return match.group(1)
    lines = normalized.split('\n')
    for i, line in enumerate(lines):
        if 'Account' in line and 'Number' in line:
            for j in range(i + 1, min(i + 4, len(lines))):
                val = lines[j].strip()
                if re.match(r'^\d{5,7}$', val):
                    return val
    return None


def _extract_richgrove_refuse(text: str) -> Optional[str]:
    """RICHGROVE REFUSE — Account No. NN-NNNNNN N format.
    Example: 02-103976 5
    """
    match = re.search(r'Account\s*No\.?\s*(\d{2}-\d{6}\s*\d)', text, re.I)
    if match:
        return match.group(1).strip()
    normalized = text.replace('\\n', '\n')
    match = re.search(r'Account\s*No\.?\s*(\d{2}-\d{6}\s*\d)', normalized, re.I)
    return match.group(1).strip() if match else None


def _extract_dolls_disposal(text: str) -> Optional[str]:
    """Doll's Disposal LLC — Customer ID followed by 12-digit value.
    Example: Customer ID 123990032003
    """
    normalized = text.replace('\\n', '\n')
    match = re.search(r'Customer\s*ID:?\s*(\d{9,15})', normalized, re.I)
    if match:
        return match.group(1)
    # Also check ID#: format (TrashBilling)
    match = re.search(r'ID\s*#:?\s*(\d{9,15})', normalized, re.I)
    return match.group(1) if match else None


def _extract_pulaski_county(text: str) -> Optional[str]:
    """PULASKI COUNTY PSA — ACCOUNT NUMBER label with NN-NN format (same number repeated).
    Example: 700027-700027 → extract 700027
    """
    normalized = text.replace('\\n', '\n')
    # Pattern 1: Hyphenated pair (700027-700027)
    match = re.search(r'ACCOUNT\s*NUMBER.*?(\d{6})-\1', normalized, re.I)
    if match:
        return match.group(1)
    # Pattern 2: Standalone 6-digit near ACCOUNT NUMBER
    lines = normalized.split('\n')
    for i, line in enumerate(lines):
        if 'ACCOUNT NUMBER' in line.upper():
            for j in range(i + 1, min(i + 6, len(lines))):
                match = re.search(r'(\d{6})', lines[j])
                if match:
                    return match.group(1)
    return None


# ============================================================
# NEW VENDOR EXTRACTION FUNCTIONS (March 9 — invoice processing gaps)
# ============================================================

def _extract_upper_valley_disposal(text: str) -> Optional[str]:
    """Format: 5-digit account number after 'Account Number' or 'Site Act Nbr'
    Examples: 23496
    Layout: Account Number\\n23496 (label on one line, value on next)
    Also: Site Act Nbr: 23496
    """
    m = re.search(
        r'(?:Site\s*Act\s*Nbr|Account\s*Number)[:\s]*(?:\\n|\s)*(\d{4,6})',
        text, re.I,
    )
    return m.group(1) if m else None


def _extract_town_of_apple_valley(text: str) -> Optional[str]:
    """Format: NN-XX NNNNNN (digits-dash-letters-space-digits)
    Examples: 06-AC 342486
    Layout: ACCOUNT NUMBER\\n...\\n06-AC 342486
    """
    m = re.search(r'(\d{2}-[A-Z]{2}\s*\d{6})', text)
    return m.group(1) if m else None


def _extract_kootenai_county(text: str) -> Optional[str]:
    """Format: NN-NNNNN.NN (digits-dash-digits, optional .NN)
    Examples: 10-86893.00, 10-80606.00
    Layout: Acct No: 10-86893.00 or Account No:\\n10-80606.00
    """
    m = re.search(
        r'(?:Acct|Account)\s*No:?\s*(?:\\n|\s)*(\d{2}-\d{5}(?:\.\d{2})?)',
        text, re.I,
    )
    return m.group(1) if m else None


def _extract_walker_lake_disposal(text: str) -> Optional[str]:
    """Format: Short numeric account (3-6 digits) after 'Account #'
    Examples: 375
    Layout: Account # 375 (inline)
    """
    m = re.search(r'Account\s*#\s*(\d{3,6})', text, re.I)
    return m.group(1) if m else None


def _extract_c_and_d_disposal(text: str) -> Optional[str]:
    """Format: NN-NNNNNNNN (2-dash-8 digits)
    Examples: 97-00457642, 97-0045764 2 (OCR space artifact)
    Layout: Account Number\\n97-00457642
    """
    # Clean match: 2-digit dash 8-digit
    m = re.search(r'\b(\d{2}-\d{8})\b', text)
    if m:
        return m.group(1)
    # OCR space artifact: 97-0045764 2 (space before last digit)
    m = re.search(r'(\d{2}-\d{7})\s+(\d)\b', text)
    if m:
        return m.group(1) + m.group(2)
    return None


def _extract_cogent_waste(text: str) -> Optional[str]:
    """Format: 7-digit account number
    Examples: 4605300
    Layout: Account Number\\n4605300 and Act Nbr: 4605300
    """
    m = re.search(
        r'(?:Account\s*Number|Act\s*Nbr)[:\s]*(?:\\n|\s)*(\d{7})',
        text, re.I,
    )
    return m.group(1) if m else None


def _extract_tacoma_public_utilities(text: str) -> Optional[str]:
    """Format: 9-digit account number after 'Account #'
    Examples: 300106553
    Layout: Account #\\n300106553
    """
    m = re.search(r'Account\s*#\s*(?:\\n|\s)*(\d{9})', text, re.I)
    return m.group(1) if m else None


# ============================================================
# v9.3 NEW / UPDATED VENDOR EXTRACTION FUNCTIONS (2026-03-11)
# Source: bill image review — 10 vendors
# ============================================================

def _extract_waste_pro_v2(text: str) -> Optional[str]:
    """Waste Pro — v2 adds 'Account Details' label format.
    Merges base engine logic + new Account Details format from bill review.
    Formats:
      1. Account Details: NNNNNN (NEW from bill review)
      2. Account Number: NNNNNN (inline)
      3. Account #/ Invoice#: NNNNNN/NNNNNNNNNN (slash-separated)
      4. Any 'Account' label + 4-7 digit value within 20 lines (base engine)
    Examples: 168855, 213309, 065996
    """
    if 'Recology' in text:
        return None

    normalized = text.replace('\\n', '\n')

    # Format 1 (NEW): Account Details label
    match = re.search(r'Account\s*Details[:\s]*(\d{4,7})', normalized, re.I)
    if match:
        return match.group(1)

    # Format 2: Slash-separated (Account #/ Invoice#:\n{acct}/{inv})
    match = re.search(r'Account\s*#/?.*Invoice.*?:?\s*\n?\s*(\d{4,7})\s*/\s*\d+', normalized, re.I)
    if match:
        return match.group(1)

    # Format 3: Inline Account Number: NNNNNN
    match = re.search(r'Account\s*Number:?\s*(\d{4,7})', normalized, re.I)
    if match:
        return match.group(1)

    # Format 4 (from base engine): Any 'Account' label + scan 20 lines
    lines = normalized.split('\n')
    for i, line in enumerate(lines):
        if 'Account' in line:
            for j in range(i, min(i + 20, len(lines))):
                val = lines[j].strip()
                # Slash-separated
                m = re.match(r'^(\d{4,7})/\d+$', val)
                if m:
                    return m.group(1)
                if re.match(r'^\d{4,7}$', val):
                    return val

    return None


def _extract_meridian_waste(text: str) -> Optional[str]:
    """Meridian Waste — v2 adds ACCT: label and Hale County 6-digit format.
    Formats:
      1. NN-NNNNNNN (70-0052573) — Account No./Account Number
      2. NN-NNNNNNN N (01-1275147 4) — with trailing digit
      3. NNNNNN (001809) — 6-digit, ACCT: label (Hale County sub-billing)
      4. ACCOUNT NUMBER + 6-digit (Hale County format)
    """
    normalized = text.replace('\\n', '\n')

    # Format 1: Inline — Account No. NN-NNNNNNN with optional trailing digit
    match = re.search(
        r'Account\s*(?:No\.?|Number)[:\s]*(\d{2}-\d{5,7}(?:\s*\d)?)',
        normalized, re.I,
    )
    if match:
        return match.group(1).strip()

    # Format 2: ACCT: NNNNNN (Hale County)
    match = re.search(r'ACCT:\s*(\d{4,6})', normalized, re.I)
    if match:
        return match.group(1)

    # Format 3: ACCOUNT NUMBER + 6-digit
    match = re.search(r'ACCOUNT\s*NUMBER\s*(?:PAST\s*DUE\s*AFTER)?.*?(\d{6})\b', normalized, re.I)
    if match:
        return match.group(1)

    # Format 4: Multi-line — label on one line, value within 10 lines
    lines = normalized.split('\n')
    for i, line in enumerate(lines):
        if re.search(r'Account\s*(?:No\.?|Number)|ACCT:', line, re.I):
            for j in range(i + 1, min(i + 10, len(lines))):
                val = lines[j].strip()
                # NN-NNNNNNN or NN-NNNNNNN N
                m = re.match(r'^(\d{2}-\d{5,7}(?:\s*\d)?)$', val)
                if m:
                    return m.group(1).strip()
                # 6-digit numeric
                if re.match(r'^\d{6}$', val):
                    return val

    # Format 5: Standalone NN-NNNNNNN (no label)
    match = re.search(r'\b(\d{2}-\d{7})\b', normalized)
    if match:
        return match.group(1)

    return None


def _extract_ace_recycling(text: str) -> Optional[str]:
    """Ace Recycling — 5-7 digit account under 'ACCOUNT #' column header.
    Examples: 802024 (6-digit), 67298 (5-digit)
    Layout: Two-column table with ACCOUNT # as header, value before or after.
    """
    normalized = text.replace('\\n', '\n')

    # Format 1: Inline ACCOUNT # NNNNN-NNNNNNN
    match = re.search(r'ACCOUNT\s*#\s*:?\s*(\d{5,7})', normalized, re.I)
    if match:
        return match.group(1)

    # Format 2: Multi-line — ACCOUNT # header, value forward or backward
    lines = normalized.split('\n')
    for i, line in enumerate(lines):
        if re.search(r'ACCOUNT\s*#', line, re.I):
            # Forward search
            for j in range(i + 1, min(i + 8, len(lines))):
                val = lines[j].strip()
                if re.match(r'^\d{5,7}$', val):
                    return val
            # Backward search (two-column: value before label)
            for j in range(max(0, i - 5), i):
                val = lines[j].strip()
                if re.match(r'^\d{5,7}$', val):
                    return val

    return None


def _extract_gfl(text: str) -> Optional[str]:
    """GFL — all account formats (v3: adds backward search + ACCOUNT NO: label).
    Formats:
      1. 1-2 alpha + 4-8 digit (KZ5645, AJ046815, UK829605) under CUSTOMER/ACCOUNT #
      2. 9-digit numeric (002294947) under ACCOUNT NUMBER:
      3. 7-digit numeric (4663301) under ACCOUNT NO: (First Piedmont subsidiary)
      4. Two-column OCR: value BEFORE label (KZ5645\\nCUSTOMER #:)
    """
    normalized = text.replace('\\n', '\n')
    acct_re = r'[A-Z]{1,2}\d{4,8}|\d{7,9}'

    # Format 1: ACCOUNT NUMBER: or ACCOUNT NO: with value (inline)
    match = re.search(r'ACCOUNT\s*(?:NUMBER|NO\.?)\s*:?\s*(' + acct_re + r')', normalized, re.I)
    if match:
        return match.group(1).upper()

    # Format 2: Inline CUSTOMER # or ACCOUNT # with value
    match = re.search(r'(?:CUSTOMER|ACCOUNT)\s*#\s*:?\s*(' + acct_re + r')', normalized, re.I)
    if match:
        return match.group(1).upper()

    # Format 3: Multi-line — search forward AND backward from label
    lines = normalized.split('\n')
    for i, line in enumerate(lines):
        if re.search(r'(?:CUSTOMER|ACCOUNT)\s*(?:#|NUMBER|NO)', line, re.I):
            # Search forward (value after label)
            for j in range(i + 1, min(i + 8, len(lines))):
                val = lines[j].strip()
                m = re.match(r'^(' + acct_re + r')$', val)
                if m:
                    return m.group(1).upper()
            # Search backward (two-column: value before label)
            for j in range(max(0, i - 5), i):
                val = lines[j].strip()
                m = re.match(r'^(' + acct_re + r')$', val)
                if m:
                    return m.group(1).upper()

    return None


def _extract_solid_waste_authority_v2(text: str) -> Optional[str]:
    """Solid Waste Authority — v2 adds numeric-only formats.
    Formats:
      1. RSA001938 (3-letter prefix + 6 digits, 'CUSTOMER NO')
      2. 082611 (6-digit, 'ACCOUNT NO.')
      3. 3055 (4-digit, 'ACCOUNT NUMBER:')
    """
    normalized = text.replace('\\n', '\n')

    # Format 1: 2-3 letter prefix + 4-6 digits (RSA001938, CMA1868)
    match = re.search(r'CUSTOMER\s*NO\.?\s*([A-Z]{2,3}\d{4,6})', normalized, re.I)
    if match:
        return match.group(1).upper()

    # Format 2: ACCOUNT NO. with 4-6 digit value (inline)
    match = re.search(
        r'ACCOUNT\s*(?:NO\.?|NUMBER)\s*:?\s*(\d{4,6})',
        normalized, re.I,
    )
    if match:
        return match.group(1)

    # Format 3: Multi-line — label then value
    lines = normalized.split('\n')
    for i, line in enumerate(lines):
        if re.search(r'(?:ACCOUNT\s*(?:NO|NUMBER)|CUSTOMER\s*NO)', line, re.I):
            for j in range(i + 1, min(i + 8, len(lines))):
                val = lines[j].strip()
                # Prefixed format (RSA001938, CMA1868)
                if re.match(r'^[A-Z]{2,3}\d{4,6}$', val, re.I):
                    return val.upper()
                # Numeric format (082611, 3055)
                if re.match(r'^\d{4,6}$', val):
                    return val

    return None


def _extract_casella_v2(text: str) -> Optional[str]:
    """Casella — v3 adds Save That Stuff 7-digit numeric format.
    All formats:
      1. KF042668 / KB350946 (2 alpha + 6 digit, 'CUSTOMER #')
      2. K/KI/KR prefix + 7-9 digits (KI00008718)
      3. HS-NNNNN (HS-36966)
      4. NN-NNNNN N (81-39019 6)
      5. NNNNNNN (1053000) — 7-digit, 'Account Number' (Save That Stuff subsidiary)
    """
    if 'PRICE CONFIRMATION' in text.upper():
        return None
    normalized = text.replace('\\n', '\n')
    lines = normalized.split('\n')

    # Save That Stuff format: Account Number + 7-digit numeric
    for i, line in enumerate(lines):
        if re.search(r'Account\s*Number', line, re.I):
            m = re.search(r'Account\s*Number\s*:?\s*(\d{7})', line, re.I)
            if m:
                return m.group(1)
            for j in range(i + 1, min(i + 6, len(lines))):
                val = lines[j].strip()
                if re.match(r'^\d{7}$', val):
                    return val

    for i, line in enumerate(lines):
        upper = line.upper()
        if 'CUSTOMER NUMBER' in upper or 'CUSTOMER #' in upper or 'CUST#:' in upper:
            # Same line: 2 alpha + 6 digit (KF042668, KB350946)
            m = re.search(r'(?:CUSTOMER\s*(?:NUMBER|#)|CUST#:?)\s*_*([A-Z]{2}\d{6})\b', line, re.I)
            if m:
                return m.group(1).upper()
            # Same line: HS-NNNNN
            m = re.search(r'(?:CUSTOMER\s*(?:NUMBER|#)|CUST#:?)\s*_*([A-Z]{2}-\d{4,6})\b', line, re.I)
            if m:
                return m.group(1).strip()
            # Same line: K/KI/KR prefix
            m = re.search(r'(?:CUSTOMER\s*(?:NUMBER|#)|CUST#:?)\s*_*(K[IRBFA-Z]?\d{7,9})', line, re.I)
            if m:
                return m.group(1).upper()
            # Same line: NN-NNNNN N
            m = re.search(r'(\d{2}-\d{5}\s*\d)', line)
            if m:
                return m.group(1).strip()
            # Next lines (two-column layout)
            for j in range(i + 1, min(i + 6, len(lines))):
                val = lines[j].strip()
                # 2 alpha + 6 digit
                if re.match(r'^[A-Z]{2}\d{6}$', val, re.I):
                    return val.upper()
                # K-prefix
                if re.match(r'^K[IRBFA-Z]?\d{7,9}$', val, re.I):
                    return val.upper()
                if re.match(r'^\d{10}$', val):
                    return val
                m = re.search(r'(\d{2}-\d{5}\s*\d)', val)
                if m:
                    return m.group(1).strip()
                # HS-NNNNN format
                m = re.match(r'^[A-Z]{2}-\d{4,6}$', val, re.I)
                if m:
                    return val.strip()
    return None


def _extract_best_way_disposal(text: str) -> Optional[str]:
    """Best Way Disposal — v2 adds 9-digit numeric format.
    Formats:
      1. X-NNNNNN (A-204017, R-208924) — original from bill review
      2. NNNNNNNNN (101431503) — 9-digit numeric, most common format
    Labels: 'Account Number', 'ActNbr:'
    """
    normalized = text.replace('\\n', '\n')

    # Format 1: Inline — Account Number: A-204017 (letter-dash-6digit)
    match = re.search(r'Account\s*Number[:\s]*([A-Z]-\d{6})', normalized, re.I)
    if match:
        return match.group(1).upper()

    # Format 2: Inline — Account Number: 101431503 (9-digit numeric)
    match = re.search(r'Account\s*Number[:\s]*(\d{9})', normalized, re.I)
    if match:
        return match.group(1)

    # Format 3: ActNbr: 101431503 (line-item reference)
    match = re.search(r'ActNbr:\s*(\d{9})', normalized, re.I)
    if match:
        return match.group(1)

    # Format 4: Multi-line — label then value
    lines = normalized.split('\n')
    for i, line in enumerate(lines):
        if re.search(r'Account\s*Number', line, re.I):
            for j in range(i + 1, min(i + 8, len(lines))):
                val = lines[j].strip()
                if re.match(r'^[A-Z]-\d{6}$', val, re.I):
                    return val.upper()
                if re.match(r'^\d{9}$', val):
                    return val

    return None


def _extract_fcc_environmental(text: str) -> Optional[str]:
    """FCC Environmental — v2 adds Houston subsidiary format.
    Formats:
      1. XXNNNNNNNN (TS00148524) — 2 alpha + 8 digit, 'Customer ID:'
      2. NNNNN (25489) — 4-6 digit, 'ACCOUNT #' (Houston Waste Services subsidiary)
    """
    normalized = text.replace('\\n', '\n')

    # Format 1: Inline — Customer ID: TS00148524
    match = re.search(r'Customer\s*ID[:\s]*([A-Z]{2}\d{8})', normalized, re.I)
    if match:
        return match.group(1).upper()

    # Format 2: Inline — ACCOUNT # NNNNN (Houston subsidiary)
    match = re.search(r'ACCOUNT\s*#[:\s]*(\d{4,6})', normalized, re.I)
    if match:
        return match.group(1)

    # Format 3: Multi-line — label then value (extended to 10 lines for two-column layouts)
    lines = normalized.split('\n')
    for i, line in enumerate(lines):
        if re.search(r'Customer\s*ID', line, re.I):
            for j in range(i + 1, min(i + 10, len(lines))):
                val = lines[j].strip()
                if re.match(r'^[A-Z]{2}\d{8}$', val, re.I):
                    return val.upper()
        if re.search(r'ACCOUNT\s*#', line, re.I):
            for j in range(i + 1, min(i + 8, len(lines))):
                val = lines[j].strip()
                if re.match(r'^\d{4,6}$', val):
                    return val

    return None


def _extract_robinson_waste_v2(text: str) -> Optional[str]:
    """Robinson Waste — v2 adds Customer ID format (alpha + 4-digit).
    Merges base engine logic + new Customer ID format from bill review.
    All formats:
      1. C8767 (1 alpha + 4 digit, 'Customer ID') — NEW from bill review
      2. ACCOUNT NO. NNNN (NG invoice format, inline)
      3. NNNNN.NNN or NNNNN-NNN (dotted/dashed account)
      4. 4-5 digit before ACCOUNT NO. label (header table format)
    """
    if 'CUSTOMER ISSUE TICKET' in text.upper():
        return None

    normalized = text.replace('\\n', '\n')

    # Format 1 (NEW): Customer ID with alpha + digit (C8767)
    match = re.search(r'Customer\s*ID[:\s]*([A-Z]\d{4,5})', normalized, re.I)
    if match:
        return match.group(1).upper()

    # Format 2 (from base engine): ACCOUNT NO. NNNN (inline)
    match = re.search(r'ACCOUNT\s*NO\.?\s*(\d{4,5})\b', normalized, re.I)
    if match:
        return match.group(1)

    lines = normalized.split('\n')

    # Multi-line Customer ID
    for i, line in enumerate(lines[:25]):
        if re.search(r'Customer\s*ID', line, re.I):
            for j in range(i + 1, min(i + 4, len(lines))):
                val = lines[j].strip()
                if re.match(r'^[A-Z]\d{4,5}$', val, re.I):
                    return val.upper()

    # Format 3 (from base engine): NNNNN.NNN or NNNNN-NNN
    for line in lines[:25]:
        match = re.search(r'\b(\d{5}[\.\-]\d{1,3})\b', line)
        if match:
            return match.group(1)

    # Format 4 (from base engine): Value BEFORE ACCOUNT NO. label
    for i, line in enumerate(lines[:20]):
        if 'ACCOUNT NO' in line.upper():
            for j in range(max(0, i - 6), i):
                val = lines[j].strip()
                if re.match(r'^\d{4,5}$', val):
                    return val
            # Also check after
            for j in range(i + 1, min(i + 5, len(lines))):
                val = lines[j].strip()
                if re.match(r'^\d{4,5}$', val):
                    return val

    return None


def _extract_city_of_north_las_vegas(text: str) -> Optional[str]:
    """City of North Las Vegas — government utility with customer/account numbers.
    Examples: 2096328 (7-digit), 137595 (6-digit)
    Labels: 'Customer Number', 'Account Number', 'Account #'
    """
    normalized = text.replace('\\n', '\n')

    # Format 1: Inline — Customer/Account Number: NNNNNNN
    match = re.search(
        r'(?:Customer|Account)\s*(?:Number|#)[:\s]*(\d{6,8})',
        normalized, re.I,
    )
    if match:
        return match.group(1)

    # Format 2: Multi-line — label then value
    lines = normalized.split('\n')
    for i, line in enumerate(lines):
        if re.search(r'(?:Customer|Account)\s*(?:Number|#)', line, re.I):
            for j in range(i + 1, min(i + 6, len(lines))):
                val = lines[j].strip()
                if re.match(r'^\d{6,8}$', val):
                    return val

    return None


def _extract_county_hauling(text: str) -> Optional[str]:
    """County Hauling — two sub-vendor formats.
    Formats:
      1. NNNN-NNNNNN (6470-173391) — Waste Connections/Lake County district-account
      2. NNNNN or NNNNNN (45611, 161729) — County Hauling proper
    Label: 'ACCOUNT NO.' or 'Acct #'
    """
    normalized = text.replace('\\n', '\n')

    # Format 1: Inline Acct # with district-account format
    match = re.search(r'Acct\s*#\s*(\d{4,6}-\d{4,6})', normalized, re.I)
    if match:
        return match.group(1)

    # Format 2: Inline ACCOUNT NO. with value
    match = re.search(r'ACCOUNT\s*NO\.?\s*:?\s*(\d{4,6}(?:-\d{4,6})?)', normalized, re.I)
    if match:
        return match.group(1)

    # Format 3: Multi-line
    lines = normalized.split('\n')
    for i, line in enumerate(lines):
        if re.search(r'ACCOUNT\s*NO|Acct\s*#', line, re.I):
            for j in range(i + 1, min(i + 8, len(lines))):
                val = lines[j].strip()
                if re.match(r'^\d{4,6}-\d{4,6}$', val):
                    return val
                if re.match(r'^\d{5,6}$', val):
                    return val

    return None


# ============================================================
# v9.3c — Batch 2 pattern fixes (2026-03-11)
# Root cause: label variants, digit count mismatches, literal \\n
# ============================================================

def _extract_apex_waste_fixed(text: str) -> Optional[str]:
    """Apex Waste — base expects ACCOUNT # + 6-12 digit, but some invoices
    use CUSTOMER NO + alpha-prefix format (DM8468). Two-column layout:
    INVOICE NUMBER / CUSTOMER NO headers, then values offset 2-4 lines later.
    """
    normalized = text.replace('\\n', '\n')
    lines = normalized.split('\n')
    # Format 1: CUSTOMER NO label — alpha-prefix value within 6 lines
    for i, line in enumerate(lines):
        if 'CUSTOMER NO' in line.upper():
            for j in range(i + 1, min(i + 6, len(lines))):
                val = lines[j].strip()
                if re.match(r'^[A-Z]{2}\d{4,6}$', val, re.I):
                    return val.upper()
    # Format 2 (base): ACCOUNT # + 6-12 digit
    for i, line in enumerate(lines):
        if 'ACCOUNT #' in line.upper():
            for j in range(i + 1, min(i + 8, len(lines))):
                val = lines[j].strip()
                if re.match(r'^\d{6,12}$', val):
                    return val
    # Inline
    match = re.search(r'ACCOUNT\s*#\s*(\d{6,12})', normalized, re.I)
    if match:
        return match.group(1)
    match = re.search(r'CUSTOMER\s*NO\.?\s*(\d{6,12})', normalized, re.I)
    if match:
        return match.group(1)
    return None


def _extract_black_hawk_waste_fixed(text: str) -> Optional[str]:
    """Black Hawk Waste — base expects NN-NNNNNN (6 digits after dash) but
    accounts are NN-NNNNN with trailing digit (04-33390 2).
    """
    normalized = text.replace('\\n', '\n')
    # Format 1: Account No. NN-NNNNN N (5 digits + trailing)
    match = re.search(r'Account\s*No\.?\s*(\d{2}-\d{5}\s*\d)', normalized, re.I)
    if match:
        return match.group(1).strip()
    # Format 2 (base): Account No. NN-NNNNNN
    match = re.search(r'Account\s*No\.?\s*(\d{2}-\d{6})', normalized, re.I)
    if match:
        return match.group(1)
    return None


def _extract_bruin_waste_fixed(text: str) -> Optional[str]:
    """Bruin Waste Management — base expects literal \\n + 6-digit. Some invoices
    use CUSTOMER ACT NBR label + 8-digit (13269000).
    """
    normalized = text.replace('\\n', '\n')
    # Format 1: CUSTOMER ACT NBR + 8-digit
    match = re.search(r'CUSTOMER\s*ACT\s*NBR\s*\n?\s*(\d{7,9})', normalized, re.I)
    if match:
        return match.group(1)
    # Format 2: CUSTOMER NO + INVOICE DATE header pattern
    lines = normalized.split('\n')
    for i, line in enumerate(lines):
        if re.search(r'CUSTOMER\s*(?:NO|ACT\s*NBR)', line, re.I):
            for j in range(i + 1, min(i + 6, len(lines))):
                val = lines[j].strip()
                if re.match(r'^\d{6,9}$', val):
                    return val
    # Format 3: QUICK PAY CODE + 6-digit (base)
    match = re.search(r'QUICK\s*PAY\s*CODE\s*\n?\s*(\d{6})', normalized, re.I)
    if match:
        return match.group(1)
    return None


def _extract_cwpm_fixed(text: str) -> Optional[str]:
    """CWPM — base expects literal \\n column headers. Actual OCR has real
    newlines. Account 20019800 appears 4-6 lines BEFORE "Account Summary"
    label in two-column layout.
    """
    normalized = text.replace('\\n', '\n')
    lines = normalized.split('\n')
    # Format 1: Account Summary block — 8-digit standalone near label (extended back search)
    for i, line in enumerate(lines):
        if 'Account Summary' in line or 'Account Number' in line:
            for j in range(max(0, i - 6), min(i + 10, len(lines))):
                val = lines[j].strip()
                if re.match(r'^\d{8}$', val):
                    return val
    # Format 2: Inline Account Number: 8-digit
    match = re.search(r'Account\s*Number[:\s]*(\d{8})', normalized, re.I)
    if match:
        return match.group(1)
    return None


def _extract_city_waste_fixed(text: str) -> Optional[str]:
    """City Waste — multiple sub-companies with different formats:
    - Houston: ACCOUNT # 5648 (4-digit)
    - Coastal Compaction: Account Number: 014550 (6-digit)
    - New York (City Waste Services): CUSTOMER NO. column header + 7-digit
    - Base: Customer # NN-NNNNN N
    """
    normalized = text.replace('\\n', '\n')
    # Format 1 (base): Customer # NN-NNNNN N
    match = re.search(r'Customer\s*#[:\s]*(\d{2}-\d{4,5}\s*\d)', normalized, re.I)
    if match:
        return match.group(1).strip()
    # Format 2: ACCOUNT # + 4-6 digit (Houston)
    match = re.search(r'ACCOUNT\s*#\s*\n?\s*(\d{4,6})', normalized, re.I)
    if match:
        return match.group(1)
    # Format 3: Account Number: 5-7 digit (Coastal Compaction)
    match = re.search(r'Account\s*Number[:\s]*(\d{5,7})', normalized, re.I)
    if match:
        return match.group(1)
    # Format 4: CUSTOMER NO. column header (New York), value on data line
    lines = normalized.split('\n')
    for i, line in enumerate(lines):
        if 'CUSTOMER NO' in line.upper() or 'CUSTOMER P.O' in line.upper():
            for j in range(i + 1, min(i + 10, len(lines))):
                val = lines[j].strip()
                # 7-digit customer number (NY format)
                if re.match(r'^\d{7}$', val):
                    return val
                # Embedded in data line: "01.01.25 1042009"
                m = re.search(r'\d{2}\.\d{2}\.\d{2}\s+(\d{7})\b', val)
                if m:
                    return m.group(1)
    # Format 5: ACCOUNT # multi-line
    for i, line in enumerate(lines):
        if re.search(r'ACCOUNT\s*#|Account\s*Number', line, re.I):
            for j in range(i + 1, min(i + 6, len(lines))):
                val = lines[j].strip()
                if re.match(r'^\d{4,7}$', val):
                    return val
    return None


def _extract_city_of_jackson_fixed(text: str) -> Optional[str]:
    """City of Jackson — base expects literal \\n + 7-digit. Some invoices
    use N-NNNNNNN-NN format (1-7304434-01) and real newlines.
    """
    normalized = text.replace('\\n', '\n')
    # Format 1: N-NNNNNNN-NN (administrative fee format)
    match = re.search(r'(\d-\d{7}-\d{2})', normalized)
    if match:
        return match.group(1)
    # Format 2: Account Number label + 7-digit value (multi-line)
    lines = normalized.split('\n')
    for i, line in enumerate(lines):
        if re.search(r'Account\s*Number|CUSTOMER\s*NO', line, re.I):
            for j in range(i + 1, min(i + 10, len(lines))):
                val = lines[j].strip()
                if re.match(r'^\d{7}$', val):
                    return val
                # Also try N-NNNNNNN-NN on data lines
                m = re.search(r'(\d-\d{7}-\d{2})', val)
                if m:
                    return m.group(1)
    # Format 3 (base): 7-digit near service address
    match = re.search(r'\n(\d{7})\n\d{3}\s+[A-Z]', normalized)
    if match:
        return match.group(1)
    return None


def _extract_econo_waste_fixed(text: str) -> Optional[str]:
    """Econo Waste — base expects Account # / Acct # but OCR uses ACCOUNT NO.
    label with two-column layout.
    """
    normalized = text.replace('\\n', '\n')
    # Format 1: ACCOUNT NO. label (inline or multi-line)
    match = re.search(r'ACCOUNT\s*NO\.?\s*(\d{4,6})', normalized, re.I)
    if match:
        return match.group(1)
    # Format 2: Account # / Acct # (base)
    match = re.search(r'(?:Account|Acct)\s*#:?\s*(\d{4,6})', normalized, re.I)
    if match:
        return match.group(1)
    # Multi-line: ACCOUNT NO. label then value
    lines = normalized.split('\n')
    for i, line in enumerate(lines):
        if re.search(r'ACCOUNT\s*NO|Account\s*#|Acct\s*#', line, re.I):
            for j in range(i + 1, min(i + 8, len(lines))):
                val = lines[j].strip()
                if re.match(r'^\d{4,6}$', val):
                    return val
            # Backward search (two-column: value before label)
            for j in range(max(0, i - 5), i):
                val = lines[j].strip()
                if re.match(r'^\d{4,6}$', val):
                    return val
    return None


def _extract_frontier_waste_fixed(text: str) -> Optional[str]:
    """Frontier Waste — base expects ACCOUNT # + 6-digit. But many invoices
    use QUICK PAY CODE label + 5-digit (46137).
    """
    normalized = text.replace('\\n', '\n')
    # Format 1: QUICK PAY CODE + 5-6 digit
    match = re.search(r'QUICK\s*PAY\s*CODE\s*\n?\s*(\d{5,6})', normalized, re.I)
    if match:
        return match.group(1)
    # Format 2: ACCOUNT # + 5-6 digit (inline or multi-line)
    match = re.search(r'ACCOUNT\s*#\s*\n?\s*(\d{5,6})', normalized, re.I)
    if match:
        return match.group(1)
    # Multi-line
    lines = normalized.split('\n')
    for i, line in enumerate(lines):
        if re.search(r'QUICK\s*PAY\s*CODE|ACCOUNT\s*#', line, re.I):
            for j in range(i + 1, min(i + 6, len(lines))):
                val = lines[j].strip()
                if re.match(r'^\d{5,6}$', val):
                    return val
    return None


def _extract_gulf_coast_containers_fixed(text: str) -> Optional[str]:
    """Gulf Coast Containers — base expects literal \\n between CUSTOMER NO.
    and value. OCR has actual newlines + columnar layout.
    """
    normalized = text.replace('\\n', '\n')
    # Format 1: Inline CUSTOMER NO. + 4-digit
    match = re.search(r'CUSTOMER\s*NO\.?\s*(\d{3,5})', normalized, re.I)
    if match:
        return match.group(1)
    # Format 2: Multi-line — CUSTOMER NO. header, value in data row
    lines = normalized.split('\n')
    for i, line in enumerate(lines):
        if 'CUSTOMER NO' in line.upper():
            # Find the data row: look for a standalone 3-5 digit number
            for j in range(i + 1, min(i + 12, len(lines))):
                val = lines[j].strip()
                if re.match(r'^\d{3,5}$', val):
                    return val
                # Also check embedded in data line (e.g., "3401\t0\tSERVICE")
                m = re.match(r'^(\d{3,5})\b', val)
                if m and not re.match(r'^\d{5,}$', val):
                    return m.group(1)
    return None


def _extract_kahut_waste_fixed(text: str) -> Optional[str]:
    """Kahut Waste — base expects inline Acct # + NNNN-NNNNNNNN. But OCR uses
    columnar headers (ACCOUNT NO.) + inline Acct #NNNNNNNN.
    """
    normalized = text.replace('\\n', '\n')
    # Format 1: Acct #NNNNNNNN (inline, 8-digit after Acct #)
    match = re.search(r'Acct\s*#(\d{7,9})', normalized, re.I)
    if match:
        return match.group(1)
    # Format 2: NNNN-NNNNNNNN (district-account composite, inline)
    match = re.search(r'(\d{4}-\d{7,9})', normalized)
    if match:
        return match.group(1)
    # Format 3: DISTRICT NO. NNNN + ACCOUNT NO. header → composite
    district = None
    lines = normalized.split('\n')
    for line in lines:
        m = re.search(r'DISTRICT\s*NO\.?\s*(\d{4})', line, re.I)
        if m:
            district = m.group(1)
            break
    if district:
        # Look for account portion near ACCOUNT NO. label
        for i, line in enumerate(lines):
            if 'ACCOUNT NO' in line.upper():
                for j in range(i + 1, min(i + 10, len(lines))):
                    val = lines[j].strip()
                    # Full composite already present
                    m = re.match(r'^(\d{4}-\d{7,9})$', val)
                    if m:
                        return m.group(1)
                    # Just the account portion
                    if re.match(r'^\d{7,9}$', val):
                        return f"{district}-{val}"
    return None


def _extract_liberty_waste_fixed(text: str) -> Optional[str]:
    """Liberty Waste — base expects NN-NNNNN N format. But many invoices use
    CUSTOMER NO + 6-digit (011861).
    """
    normalized = text.replace('\\n', '\n')
    # Format 1: CUSTOMER NO + 6-digit
    match = re.search(r'CUSTOMER\s*NO\.?\s*\n?\s*(\d{6})', normalized, re.I)
    if match:
        return match.group(1)
    # Format 2 (base): Account No. + NN-NNNNN N
    match = re.search(r'Account\s*No\.?\s*(\d{2}-\d{5}\s*\d)', normalized, re.I)
    if match:
        return match.group(1).strip()
    # Format 3 (base): Customer # + NN-NNNNN N
    match = re.search(r'Customer\s*#[:\s]*(\d{2}-\d{5}\s*\d)', normalized, re.I)
    if match:
        return match.group(1).strip()
    # Multi-line: CUSTOMER NO label, value on next line
    lines = normalized.split('\n')
    for i, line in enumerate(lines):
        if re.search(r'CUSTOMER\s*NO', line, re.I):
            for j in range(i + 1, min(i + 4, len(lines))):
                val = lines[j].strip()
                if re.match(r'^\d{5,7}$', val):
                    return val
    return None


def _extract_marborg_fixed(text: str) -> Optional[str]:
    """Marborg — base expects N-NNNNNN-N (7+ chars). But some accounts are
    shorter: 7-650 (N-NNN) or 8-73932 (N-NNNNN).
    """
    normalized = text.replace('\\n', '\n')
    # Format 1: Customer Number + N-NNN to N-NNNNNN N (flexible length)
    match = re.search(
        r'Customer\s*Number[:\s]*(\d-\d{3,6}(?:\s*\d)?)',
        normalized, re.I,
    )
    if match:
        return match.group(1).strip()
    # Format 2: Multi-line — Customer Number label, value on following line
    lines = normalized.split('\n')
    for i, line in enumerate(lines):
        if 'Customer Number' in line:
            for j in range(i + 1, min(i + 6, len(lines))):
                val = lines[j].strip()
                if re.match(r'^\d-\d{3,6}(\s*\d)?$', val):
                    return val.strip()
    # Format 3 (base): Standalone N-NNNNNN N pattern
    match = re.search(r'(\d\s*-\d{3,6}\s*\d)', normalized)
    if match:
        return match.group(1).strip()
    return None


def _extract_midwest_paper_fixed(text: str) -> Optional[str]:
    """Midwest Paper — base expects inline Customer No: NNNN. But OCR uses
    CUSTOMER NO. as column header with value on data line below.
    """
    normalized = text.replace('\\n', '\n')
    # Format 1 (base): Inline Customer No: NNNN
    match = re.search(r'Customer\s*No\.?:?\s*(\d{3,5})', normalized, re.I)
    if match:
        return match.group(1)
    # Format 2: CUSTOMER NO. column header — data row follows
    lines = normalized.split('\n')
    for i, line in enumerate(lines):
        if 'CUSTOMER NO' in line.upper():
            # Look for data row with date + customer number
            for j in range(i + 1, min(i + 10, len(lines))):
                val = lines[j].strip()
                # Data row pattern: DATE CUSTOMER_NO SITE_NO
                m = re.search(r'[A-Z][a-z]{2}-\d{2}-\d{2,4}\s+(\d{3,5})\b', val)
                if m:
                    return m.group(1)
                # Standalone 3-5 digit (customer number)
                if re.match(r'^\d{3,5}$', val):
                    return val
    return None


def _extract_pacific_waste_fixed(text: str) -> Optional[str]:
    """Pacific Waste — base expects numeric-only 5-7 digit. But accounts
    use PW prefix (PW119, PW1193, PW1237).
    """
    normalized = text.replace('\\n', '\n')
    # Format 1: Account Number + PW-prefix
    match = re.search(r'Account\s*Number[:\s]*(PW\d{3,5})', normalized, re.I)
    if match:
        return match.group(1).upper()
    # Format 2 (base): Account # + 5-7 digit numeric
    match = re.search(r'(?:Account|Acct)\s*#:?\s*(\d{5,7})', normalized, re.I)
    if match:
        return match.group(1)
    # Multi-line: Account Number label, PW-prefix on next line
    lines = normalized.split('\n')
    for i, line in enumerate(lines):
        if re.search(r'Account\s*Number', line, re.I):
            for j in range(i + 1, min(i + 5, len(lines))):
                val = lines[j].strip()
                if re.match(r'^PW\d{3,5}$', val, re.I):
                    return val.upper()
                if re.match(r'^\d{5,7}$', val):
                    return val
    return None


def _extract_south_shore_disposal_fixed(text: str) -> Optional[str]:
    """South Shore Disposal — base expects 'Account Number:' but OCR uses
    ACCOUNT# (no space) and ACCT# formats.
    """
    normalized = text.replace('\\n', '\n')
    # Format 1: ACCOUNT# or ACCT# (no space before #)
    match = re.search(r'(?:ACCOUNT|ACCT)\s*#\s*(\d{6})', normalized, re.I)
    if match:
        return match.group(1)
    # Format 2 (base): Account Number: NNNNNN
    match = re.search(r'Account\s*Number[:\s]*(\d{6})', normalized, re.I)
    if match:
        return match.group(1)
    # Multi-line
    lines = normalized.split('\n')
    for i, line in enumerate(lines):
        if re.search(r'ACCOUNT\s*#|ACCT\s*#|Account\s*Number', line, re.I):
            for j in range(i + 1, min(i + 5, len(lines))):
                val = lines[j].strip()
                if re.match(r'^\d{6}$', val):
                    return val
    return None


def _extract_star_waste_fixed(text: str) -> Optional[str]:
    """Star Waste — base expects ACCOUNT NUMBER label. But many invoices use
    QUICK PAY CODE label instead (119369).
    """
    normalized = text.replace('\\n', '\n')
    # Format 1: QUICK PAY CODE + 5-7 digit
    match = re.search(r'QUICK\s*PAY\s*CODE\s*\n?\s*(\d{5,7})', normalized, re.I)
    if match:
        return match.group(1)
    # Format 2 (base): ACCOUNT NUMBER + alphanumeric
    match = re.search(r'ACCOUNT\s*NUMBER[:\s]*([A-Z0-9-]+)', normalized, re.I)
    if match:
        val = match.group(1).strip()
        if len(val) >= 4:
            return val
    # Multi-line
    lines = normalized.split('\n')
    for i, line in enumerate(lines):
        if re.search(r'QUICK\s*PAY\s*CODE|ACCOUNT\s*NUMBER', line, re.I):
            for j in range(i + 1, min(i + 6, len(lines))):
                val = lines[j].strip()
                if re.match(r'^[\dA-Z-]+$', val) and len(val) >= 4:
                    return val
    return None


def _extract_tk_trash_fixed(text: str) -> Optional[str]:
    """TK Trash — base expects 'Cust. #' (with period) + literal \\n. But
    OCR uses 'Customer #' (no period) with actual newlines.
    """
    normalized = text.replace('\\n', '\n')
    # Format 1: Customer # + NN-NNNNNN N (inline)
    match = re.search(r'Customer\s*#\s*\n?\s*(\d{2}-\d{6}\s*\d)', normalized, re.I)
    if match:
        return match.group(1).strip()
    # Format 2 (base): Cust. # + NN-NNNNNN N
    match = re.search(r'Cust\.\s*#\s*\n?\s*(\d{2}-\d{6}\s*\d)', normalized, re.I)
    if match:
        return match.group(1).strip()
    # Multi-line
    lines = normalized.split('\n')
    for i, line in enumerate(lines):
        if re.search(r'(?:Customer|Cust\.?)\s*#', line, re.I):
            for j in range(i + 1, min(i + 4, len(lines))):
                val = lines[j].strip()
                if re.match(r'^\d{2}-\d{6}\s*\d$', val):
                    return val.strip()
    return None


def _extract_wasatch_waste_fixed(text: str) -> Optional[str]:
    """Wasatch Waste — base uses broad pattern '.\\d{5}'. But OCR shows:
    - Customer Account # : 000083 (6-digit)
    - ACCOUNT NO. label
    """
    normalized = text.replace('\\n', '\n')
    # Format 1: Customer Account # : NNNNNN
    match = re.search(r'Customer\s*Account\s*#\s*:?\s*(\d{5,7})', normalized, re.I)
    if match:
        return match.group(1)
    # Format 2: ACCOUNT NO. + value
    match = re.search(r'ACCOUNT\s*NO\.?\s*(\d{5,7})', normalized, re.I)
    if match:
        return match.group(1)
    # Format 3: Account # or Acct #
    match = re.search(r'(?:Account|Acct)\s*#:?\s*(\d{5,7})', normalized, re.I)
    if match:
        return match.group(1)
    # Multi-line
    lines = normalized.split('\n')
    for i, line in enumerate(lines):
        if re.search(r'Customer\s*Account|ACCOUNT\s*NO', line, re.I):
            for j in range(i + 1, min(i + 6, len(lines))):
                val = lines[j].strip()
                if re.match(r'^\d{5,7}$', val):
                    return val
    return None


def _extract_waste_connections_fixed(text: str) -> Optional[str]:
    """Waste Connections — base expects standalone NNNN-NNNNN+ pattern. But
    OCR uses DISTRICT NO. NNNN + Acct #NNNN composite format. Also landfill
    invoices use NNNN-NNN format (shorter account portion).
    """
    normalized = text.replace('\\n', '\n')
    # Format 1 (base): Standalone NNNN-NNN+ pattern (allow 3+ digits after dash)
    match = re.search(r'(\d{4}-\d{3,9}(?:-\d{2,3})?)', normalized)
    if match:
        return match.group(1)
    # Format 2: Acct #NNNN inline → need district prefix
    district = None
    lines = normalized.split('\n')
    for line in lines:
        m = re.search(r'DISTRICT\s*NO\.?\s*(\d{4})', line, re.I)
        if m:
            district = m.group(1)
            break
    # Find account portion
    acct_match = re.search(r'Acct\s*#(\d{3,8})', normalized, re.I)
    if acct_match:
        acct = acct_match.group(1)
        if district:
            return f"{district}-{acct}"
        return acct
    # Format 3: CUSTOMER NUMBER label + 5-6 digit
    match = re.search(r'CUSTOMER\s*NUMBER\s*\n?\s*(\d{5,8})', normalized, re.I)
    if match:
        return match.group(1)
    # Multi-line: ACCOUNT NO. or CUSTOMER NUMBER header → look for value
    for i, line in enumerate(lines):
        if 'ACCOUNT NO' in line.upper() or 'CUSTOMER NUMBER' in line.upper():
            for j in range(i + 1, min(i + 10, len(lines))):
                val = lines[j].strip()
                m = re.match(r'^(\d{4}-\d{3,8})$', val)
                if m:
                    return m.group(1)
                if district and re.match(r'^\d{3,8}$', val):
                    return f"{district}-{val}"
    # Format 4: Account# label (rate notification)
    match = re.search(r'Account\s*#\s*(\d{4}-\d{3,8})', normalized, re.I)
    if match:
        return match.group(1)
    return None


def _extract_waste_services_llc_fixed(text: str) -> Optional[str]:
    """Waste Services LLC — base expects 6-digit from TrashBilling format.
    But some invoices use Account# + 5-digit (13724).
    """
    normalized = text.replace('\\n', '\n')
    # Format 1: Account# NNNNN (inline, 5-6 digit)
    match = re.search(r'Account\s*#\s*(\d{5,7})', normalized, re.I)
    if match:
        return match.group(1)
    # Format 2 (base): "account number with this hauler is NNNNNN"
    match = re.search(r'account\s*number\s*with\s*this\s*hauler\s*is\s*(\d{5,7})', normalized, re.I)
    if match:
        return match.group(1)
    # Format 3 (base): ID#: NNNNNN
    match = re.search(r'ID#:\s*\d*(\d{5,7})', normalized)
    if match:
        return match.group(1)
    # Multi-line
    lines = normalized.split('\n')
    for i, line in enumerate(lines):
        if re.search(r'Account\s*#', line, re.I):
            for j in range(i + 1, min(i + 5, len(lines))):
                val = lines[j].strip()
                if re.match(r'^\d{5,7}$', val):
                    return val
    return None


# ============================================================
# VENDOR ADDITIONS DICT
# ============================================================

VENDOR_ADDITIONS_MAR2026 = {
    # --- New vendors (March 2026) ---
    'Derby City Environmental': {
        'has_account': True,
        'format': 'XNNNN',
        'examples': ['C1504'],
        'extract': _extract_derby_city,
    },
    "Chism's Trash Service": {
        'has_account': True,
        'format': 'NNNN',
        'examples': ['9553'],
        'extract': _extract_chisms_trash,
    },
    'Woody & Sons Disposal': {
        'has_account': True,
        'format': 'NNNNN',
        'examples': ['10744'],
        'extract': _extract_woody_sons,
    },
    'Craven Ag Services': {
        'has_account': True,
        'format': 'XNNN',
        'examples': ['G528'],
        'extract': _extract_craven_ag,
    },
    'Royal Sanitation': {
        'has_account': True,
        'format': 'NNNN',
        'examples': ['5295'],
        'extract': _extract_royal_sanitation,
    },
    'Anytime Disposal Services': {
        'has_account': False,
        'format': None,
        'examples': [],
        'extract': lambda x: None,
    },
    'Tri-State Waste & Recycling': {
        'has_account': True,
        'format': 'NNNNNN',
        'examples': ['196871'],
        'extract': _extract_tri_state_waste,
    },
    'A1 Waste': {
        'has_account': True,
        'format': 'XX-NNNN-NNNN',
        'examples': ['WA-2501-6674'],
        'extract': _extract_a1_waste,
    },

    # --- Invoice processing gap closures (March 9, 2026) ---
    'Upper Valley Disposal': {
        'has_account': True,
        'format': 'NNNNN',
        'examples': ['23496'],
        'extract': _extract_upper_valley_disposal,
    },
    'Town of Apple Valley': {
        'has_account': True,
        'format': 'NN-XX NNNNNN',
        'examples': ['06-AC 342486'],
        'extract': _extract_town_of_apple_valley,
    },
    'Kootenai County Solid Waste': {
        'has_account': True,
        'format': 'NN-NNNNN.NN',
        'examples': ['10-86893.00', '10-80606.00'],
        'extract': _extract_kootenai_county,
    },
    'Walker Lake Disposal': {
        'has_account': True,
        'format': 'NNN',
        'examples': ['375'],
        'extract': _extract_walker_lake_disposal,
    },
    'C & D Disposal': {
        'has_account': True,
        'format': 'NN-NNNNNNNN',
        'examples': ['97-00457642'],
        'extract': _extract_c_and_d_disposal,
    },
    'Cogent Waste Solutions': {
        'has_account': True,
        'format': 'NNNNNNN',
        'examples': ['4605300'],
        'extract': _extract_cogent_waste,
    },
    'Tacoma Public Utilities': {
        'has_account': True,
        'format': 'NNNNNNNNN',
        'examples': ['300106553'],
        'extract': _extract_tacoma_public_utilities,
    },

    # --- Corrected vendor patterns (vendor overrides in ops_database) ---
    'Pueblo of Zuni': {
        'has_account': True,
        'format': 'X-NN',
        'examples': ['Z-10'],
        'extract': _extract_pueblo_of_zuni,
    },
    'Organix Recycling': {
        'has_account': True,
        'format': 'NNNNNNNNN',
        'examples': ['599124169'],
        'extract': _extract_organix_recycling,
    },
    "Ava's Waste Removal": {
        'has_account': False,
        'format': None,
        'examples': [],
        'extract': lambda x: None,
    },
    'Panzarella Waste': {
        'has_account': True,
        'format': 'NN-NNNN N',
        'examples': ['01-4649 9'],
        'extract': _extract_panzarella_waste,
    },

    # --- Pattern fixes (overrides from earlier additions) ---
    'CR&R': {
        'has_account': True,
        'format': 'NN-NNNNNNNNN',
        'examples': ['93-00312437'],
        'extract': _extract_crr_fixed,
    },
    'EDCO Disposal': {
        'has_account': True,
        'format': 'NN-XX NNNNNN',
        'examples': ['55-J5 729042', '25-3R 120075'],
        'extract': _extract_edco_disposal_fixed,
    },
    'Robinson Waste': {
        'has_account': True,
        'format': 'NNNNN or NNNNN.NNN',
        'examples': ['51001', '55779.64'],
        'extract': _extract_robinson_waste_fixed,
    },
    'Standard Waste': {
        'has_account': True,
        'format': 'XXX.XXXXXX or XXX-XXXXXX',
        'examples': ['UPS.NJEDI1', 'UPS-NJBAY'],
        'extract': _extract_standard_waste_fixed,
    },
    'Modern Recycling': {
        'has_account': True,
        'format': 'NNNNN',
        'examples': ['53262', '4179'],
        'extract': _extract_modern_recycling_fixed,
    },
    'Tower Compactor': {
        'has_account': True,
        'format': 'XXXNNN or XXXXXX',
        'examples': ['UPS012', 'WASOOR'],
        'extract': _extract_tower_compactor_fixed,
    },
    'Jamaica Ash': {
        'has_account': True,
        'format': 'NNNNNN',
        'examples': ['482277'],
        'extract': _extract_jamaica_ash_fixed2,
    },
    'Jamaica Ash & Rubbish': {
        'has_account': True,
        'format': 'NNNNNN',
        'examples': ['482277'],
        'extract': _extract_jamaica_ash_fixed2,
    },
    'Jamaicaash': {
        'has_account': True,
        'format': 'NNNNNN',
        'examples': ['482277'],
        'extract': _extract_jamaica_ash_fixed2,
    },

    # ==========================================================================
    # v9.2 — Pattern fixes for 2026-02-12 batch extraction failures (Gap 6)
    # Root cause: two-column OCR layouts + literal \\n in text
    # ==========================================================================

    # JP Mascaro (13 failures): Pattern required exactly 6 digits but some accounts
    # are 5 digits (Berks division). Souderton division has no label.
    'JP Mascaro': {
        'has_account': True,
        'format': 'NNNNN or NNNNNN',
        'examples': ['88395', '187877', '132402'],
        'extract': _extract_jp_mascaro_fixed,
    },

    # Friedman Recycling (10 failures): Hard-coded line index 5 didn't work.
    # Account appears right after "FRIEDMAN" in two-column layout.
    'Friedman Recycling': {
        'has_account': True,
        'format': 'NNNNNNNN or NNNNNNN',
        'examples': ['11754300', '4646006', '11751300'],
        'extract': _extract_friedman_recycling_fixed,
    },

    # Rumpke (7 failures): Feb2026 fix used inline regex but label/value are
    # on separate lines with literal \\n between them.
    'Rumpke': {
        'has_account': True,
        'format': 'NNNNNNNNNN',
        'examples': ['0201169794', '0201169786', '0101467736'],
        'extract': _extract_rumpke_fixed2,
    },

    # Stericycle (5 failures): Pattern only handled "Customer No. (Payer)" but
    # Shred-it branded invoices use "Customer ID:" with two-column layout.
    'Stericycle': {
        'has_account': True,
        'format': 'NNNNNNNNNN',
        'examples': ['3001303944', '3001304111', '3001288443'],
        'extract': _extract_stericycle_fixed,
    },

    # Capital Waste (2 failures): Pattern looked for exact "ACCOUNT" label but
    # OCR uses "CUSTOMER NUMBER" with two-column layout.
    'Capital Waste': {
        'has_account': True,
        'format': 'NNNNNNN',
        'examples': ['2914706', '2900816', '162588'],
        'extract': _extract_capital_waste_fixed,
    },

    # Casella (1 failure): Feb2026 fix uses text.split('\n') but BigQuery
    # text has literal \\n. Need to normalize before splitting.
    'Casella': {
        'has_account': True,
        'format': 'KNNNNNNNNN or XX-NNNNN N',
        'examples': ['KI00008718', 'K100008742', 'HS-36966', '81-39019 6'],
        'extract': _extract_casella_fixed2,
    },

    # ZARC Recycling (2 failures): Pattern required exactly 3 digits but
    # account 1147 is 4 digits.
    'ZARC Recycling': {
        'has_account': True,
        'format': 'NNN or NNNN',
        'examples': ['1147', '979', '992'],
        'extract': _extract_zarc_recycling_fixed,
    },

    # NK Waste (3 failures): Pattern required 5 digits but sub-vendors use
    # 3-digit (Hensley) and 12-digit (TrashBilling) formats.
    'NK Waste': {
        'has_account': True,
        'format': 'NNN-NNNNNNNNNNNN (variable)',
        'examples': ['780', '108970058963'],
        'extract': _extract_nk_waste_fixed,
    },

    # Waste Pro (3 failures): Feb2026 fix used inline-only regex but these
    # invoices use two-column layout or slash-separated format.
    'Waste Pro': {
        'has_account': True,
        'format': 'NNNNNN',
        'examples': ['213309', '065996', '246126'],
        'extract': _extract_waste_pro_fixed,
    },

    # Advance Disposal (1 failure): Literal \\n between label and value.
    'Advance Disposal': {
        'has_account': True,
        'format': 'NNNNNN',
        'examples': ['076006'],
        'extract': _extract_advance_disposal_fixed,
    },

    # Best Pick Disposal (1 failure): Literal \\n between label and value.
    'Best Pick Disposal': {
        'has_account': True,
        'format': 'NNNNNNNN',
        'examples': ['14374500', '14374502'],
        'extract': _extract_best_pick_disposal_fixed,
    },

    # City of Casper (1 failure): Uses "customer id Number" label (unusual casing).
    'City of Casper': {
        'has_account': True,
        'format': 'NNNNNNN',
        'examples': ['1591625', '202284'],
        'extract': _extract_city_of_casper_fixed,
    },

    # Jettison Environmental (1 failure): Literal \\n between label and value.
    'Jettison Environmental': {
        'has_account': True,
        'format': 'NNNNNN',
        'examples': ['109991', '204225'],
        'extract': _extract_jettison_environmental_fixed,
    },

    # Mark Dunning (1 failure): Literal \\n between label and value.
    'Mark Dunning': {
        'has_account': True,
        'format': 'NNNNNNN',
        'examples': ['1420782', '1398986', '1373624'],
        'extract': _extract_mark_dunning_fixed2,
    },

    # Recology (1 failure): Account starting with "00" not handled by prefix filters.
    'Recology': {
        'has_account': True,
        'format': 'NNNNNNNNNN',
        'examples': ['0043677855', '8100237266', '1080914879'],
        'extract': _extract_recology_fixed,
    },

    # ==========================================================================
    # v9.2 — New vendor patterns (Gap 6 Action 4)
    # ==========================================================================

    'Key Works': {
        'has_account': True,
        'format': 'NNNNNN',
        'examples': ['630100'],
        'extract': _extract_key_works,
    },
    'RICHGROVE REFUSE, INC': {
        'has_account': True,
        'format': 'NN-NNNNNN N',
        'examples': ['02-103976 5'],
        'extract': _extract_richgrove_refuse,
    },
    "Doll's Disposal LLC": {
        'has_account': True,
        'format': 'NNNNNNNNNNNN',
        'examples': ['123990032003'],
        'extract': _extract_dolls_disposal,
    },
    'PULASKI COUNTY': {
        'has_account': True,
        'format': 'NNNNNN',
        'examples': ['700027'],
        'extract': _extract_pulaski_county,
    },

    # ==========================================================================
    # v9.2 — NO_ACCOUNT vendors (Gap 6 Action 3)
    # ==========================================================================

    'WG Waste': {
        'has_account': False,
        'format': None,
        'examples': [],
        'extract': lambda x: None,
        'notes': 'Uses company name as Acc field, no numeric account numbers',
    },
    'Dumpster Pros': {
        'has_account': False,
        'format': None,
        'examples': [],
        'extract': lambda x: None,
        'notes': 'Small hauler, invoice-only (no account numbering)',
    },
    'Fix It Right Inc.': {
        'has_account': False,
        'format': None,
        'examples': [],
        'extract': lambda x: None,
        'notes': 'Equipment repair company, service forms only',
    },
    'McNeilly Wood Products Inc.': {
        'has_account': False,
        'format': None,
        'examples': [],
        'extract': lambda x: None,
        'notes': 'Pallet disposal vendor, uses PO numbers not accounts',
    },
    'Atlantic Recycling Equipment': {
        'has_account': False,
        'format': None,
        'examples': [],
        'extract': lambda x: None,
        'notes': 'Equipment repair vendor, invoice-only',
    },
    'Howard Disposal': {
        'has_account': False,
        'format': None,
        'examples': [],
        'extract': lambda x: None,
        'notes': 'Small hauler, invoice-only (no account numbering). Overrides jan2026 D-NNNN pattern which was for a different invoice format.',
    },

    # ==========================================================================
    # Historical build (2026-03-11): Vendors confirmed NO_ACCOUNT after
    # analyzing 235K invoice corpus. Overrides earlier has_account=True entries.
    # ==========================================================================
    'SmartTrash': {
        'has_account': False,
        'format': None,
        'examples': [],
        'extract': lambda x: None,
        'notes': 'Equipment monitoring vendor (sensors/cameras). 592 invoices — 0 have CNNNNN customer codes in this corpus. Overrides feb2026.',
    },
    'Specific Waste': {
        'has_account': False,
        'format': None,
        'examples': [],
        'extract': lambda x: None,
        'notes': 'Medical/hazardous waste vendor. Invoices are Certificates of Destruction or consolidated invoices without customer account numbers.',
    },
    'Redbox+': {
        'has_account': False,
        'format': None,
        'examples': [],
        'extract': lambda x: None,
        'notes': 'Roll-off dumpster rental. 473 invoices — 0 have account-like labels. Invoice-only identification.',
    },

    # ==========================================================================
    # v9.3 — New/updated vendor patterns from bill image review (2026-03-11)
    # ==========================================================================

    # Waste Pro (v2): Adds 'Account Details' label format. Overrides v9.2 entry.
    'Waste Pro': {
        'has_account': True,
        'format': 'NNNNNN',
        'examples': ['168855', '213309', '065996', '246126'],
        'extract': _extract_waste_pro_v2,
    },

    'Meridian Waste': {
        'has_account': True,
        'format': 'NN-NNNNNNN or NN-NNNNNNN N',
        'examples': ['70-0052573', '01-1275147 4'],
        'extract': _extract_meridian_waste,
    },

    'Ace Recycling': {
        'has_account': True,
        'format': 'NNNNNN',
        'examples': ['802024'],
        'extract': _extract_ace_recycling,
    },

    'GFL': {
        'has_account': True,
        'format': 'XXNNNN or XXNNNNNN',
        'examples': ['KZ5645', 'AJ046815'],
        'extract': _extract_gfl,
    },

    # Solid Waste Authority (v2): Adds 4-6 digit numeric formats.
    # Overrides jan2026 entry (RSA001938 3-letter prefix format preserved).
    'Solid Waste Authority': {
        'has_account': True,
        'format': 'XXXNNNNNN or NNNNNN or NNNN',
        'examples': ['RSA001938', '082611', '3055'],
        'extract': _extract_solid_waste_authority_v2,
    },

    # Casella (v2): Adds 2-alpha + 6-digit format (KF/KB prefixes).
    # Overrides v9.2 entry (all previous formats preserved).
    'Casella': {
        'has_account': True,
        'format': 'XXNNNNNN or KNNNNNNNNN or XX-NNNNN N',
        'examples': ['KF042668', 'KB350946', 'KI00008718', 'HS-36966', '81-39019 6'],
        'extract': _extract_casella_v2,
    },

    'Best Way Disposal': {
        'has_account': True,
        'format': 'X-NNNNNN',
        'examples': ['A-204017', 'R-208924'],
        'extract': _extract_best_way_disposal,
    },

    'FCC Environmental': {
        'has_account': True,
        'format': 'XXNNNNNNNN',
        'examples': ['TS00148524'],
        'extract': _extract_fcc_environmental,
    },

    # Robinson Waste (v2): Adds Customer ID format (alpha + 4-digit).
    # Overrides v9.2 entry (all previous formats preserved).
    'Robinson Waste': {
        'has_account': True,
        'format': 'XNNNN or NNNNN or NNNNN.NNN',
        'examples': ['C8767', '51001', '55779.64'],
        'extract': _extract_robinson_waste_v2,
    },

    'City of North Las Vegas': {
        'has_account': True,
        'format': 'NNNNNNN or NNNNNN',
        'examples': ['2096328', '137595'],
        'extract': _extract_city_of_north_las_vegas,
    },

    # ==========================================================================
    # v9.3 — NO_ACCOUNT vendors (2026-03-11, bill image review)
    # ==========================================================================

    'American Disposal Systems': {
        'has_account': False,
        'format': None,
        'examples': [],
        'extract': lambda x: None,
        'notes': 'No account numbers visible on invoices across multiple samples.',
    },
    'Wise Environmental': {
        'has_account': False,
        'format': None,
        'examples': [],
        'extract': lambda x: None,
        'notes': 'No reliable account numbers on bill images. Overrides jan2026 positional pattern.',
    },
    'ACES Disposal': {
        'has_account': False,
        'format': None,
        'examples': [],
        'extract': lambda x: None,
        'notes': 'Equipment monitoring vendor, not waste hauler. Overrides jan2026 WM-format pattern.',
    },
    'Community Disposal': {
        'has_account': False,
        'format': None,
        'examples': [],
        'extract': lambda x: None,
        'notes': 'No account numbers on bill images. Overrides jan2026 CBRE-UPS pattern.',
    },
    'Hamilton Alliance': {
        'has_account': False,
        'format': None,
        'examples': [],
        'extract': lambda x: None,
        'notes': 'No account numbers visible on invoices.',
    },
    'Priority Waste': {
        'has_account': False,
        'format': None,
        'examples': [],
        'extract': lambda x: None,
        'notes': 'Payment receipts, not bills. No account numbers.',
    },
    'Western Waste Services': {
        'has_account': False,
        'format': None,
        'examples': [],
        'extract': lambda x: None,
        'notes': 'No account number patterns visible on bill images.',
    },

    # ==========================================================================
    # v9.3b — Pattern fixes from OCR debug (2026-03-11)
    # ==========================================================================

    'County Hauling': {
        'has_account': True,
        'format': 'NNNN-NNNNNN or NNNNN',
        'examples': ['6470-173391', '45611', '161729'],
        'extract': _extract_county_hauling,
    },

    'EcoSouth': {
        'has_account': False,
        'format': None,
        'examples': [],
        'extract': lambda x: None,
        'notes': 'Payment receipts from Heartland Payment Systems portal. "Account Number" refers to bank account, not customer account.',
    },

    # ==========================================================================
    # v9.3c — Batch 2 pattern fixes (2026-03-11)
    # Label variants, digit count mismatches, literal \\n normalization
    # ==========================================================================

    'Apex Waste': {
        'has_account': True,
        'format': 'XXNNNN (DM8468) or NNNNNNNN',
        'examples': ['DM8468'],
        'extract': _extract_apex_waste_fixed,
    },

    'Black Hawk Waste': {
        'has_account': True,
        'format': 'NN-NNNNN N',
        'examples': ['04-33390 2', '04-33387 8'],
        'extract': _extract_black_hawk_waste_fixed,
    },

    'Bruin Waste Management': {
        'has_account': True,
        'format': 'NNNNNNNN (8-digit)',
        'examples': ['13269000', '13268700'],
        'extract': _extract_bruin_waste_fixed,
    },

    'CWPM': {
        'has_account': True,
        'format': 'NNNNNNNN (8-digit)',
        'examples': ['20019800'],
        'extract': _extract_cwpm_fixed,
    },

    'City Waste': {
        'has_account': True,
        'format': 'NNNN-NNNNNN or NNNN or NNNNNN',
        'examples': ['5648', '014550'],
        'extract': _extract_city_waste_fixed,
    },

    'City of Jackson': {
        'has_account': True,
        'format': 'N-NNNNNNN-NN or NNNNNNN',
        'examples': ['1-7304434-01'],
        'extract': _extract_city_of_jackson_fixed,
    },

    'Econo Waste': {
        'has_account': True,
        'format': 'NNNNN',
        'examples': ['61934'],
        'extract': _extract_econo_waste_fixed,
    },

    'Frontier Waste': {
        'has_account': True,
        'format': 'NNNNN (Quick Pay Code)',
        'examples': ['46137', '94848'],
        'extract': _extract_frontier_waste_fixed,
    },

    'Gulf Coast Containers': {
        'has_account': True,
        'format': 'NNNN',
        'examples': ['3401'],
        'extract': _extract_gulf_coast_containers_fixed,
    },

    'Kahut Waste': {
        'has_account': True,
        'format': 'NNNN-NNNNNNNN or NNNNNNNN',
        'examples': ['2021-71918806', '71918806'],
        'extract': _extract_kahut_waste_fixed,
    },

    'Liberty Waste': {
        'has_account': True,
        'format': 'NNNNNN or NN-NNNNN N',
        'examples': ['011861', '012407'],
        'extract': _extract_liberty_waste_fixed,
    },

    'Marborg': {
        'has_account': True,
        'format': 'N-NNN to N-NNNNNN N',
        'examples': ['7-650', '8-73932'],
        'extract': _extract_marborg_fixed,
    },

    'Midwest Paper': {
        'has_account': True,
        'format': 'NNNN',
        'examples': ['3799'],
        'extract': _extract_midwest_paper_fixed,
    },

    'Pacific Waste': {
        'has_account': True,
        'format': 'PWNNNN or NNNNNN',
        'examples': ['PW1193', 'PW1237', 'PW119'],
        'extract': _extract_pacific_waste_fixed,
    },

    'South Shore Disposal': {
        'has_account': True,
        'format': 'NNNNNN',
        'examples': ['164055', '164066', '164044'],
        'extract': _extract_south_shore_disposal_fixed,
    },

    'Star Waste': {
        'has_account': True,
        'format': 'NNNNNN (Quick Pay Code) or alphanumeric',
        'examples': ['119369', '10977'],
        'extract': _extract_star_waste_fixed,
    },

    'TK Trash': {
        'has_account': True,
        'format': 'NN-NNNNNN N',
        'examples': ['75-601867 3', '75-584760 1'],
        'extract': _extract_tk_trash_fixed,
    },

    'Wasatch Waste': {
        'has_account': True,
        'format': 'NNNNNN',
        'examples': ['000083'],
        'extract': _extract_wasatch_waste_fixed,
    },

    'Waste Connections': {
        'has_account': True,
        'format': 'NNNN-NNNN or NNNN-NNNNN+',
        'examples': ['2311-0223', '6370-5434'],
        'extract': _extract_waste_connections_fixed,
    },

    'Waste Services LLC': {
        'has_account': True,
        'format': 'NNNNN or NNNNNN',
        'examples': ['13724'],
        'extract': _extract_waste_services_llc_fixed,
    },

    # NO_ACCOUNT vendors (user confirmed "none" / "not a bill" in batch 2)
    'Bliss Environmental': {
        'has_account': False,
        'format': None,
        'examples': [],
        'extract': lambda x: None,
        'notes': 'No account numbers visible across 3 bill samples. Overrides base engine.',
    },
    'Earthwise Waste Solutions': {
        'has_account': False,
        'format': None,
        'examples': [],
        'extract': lambda x: None,
        'notes': 'No account numbers visible across 3 bill samples. Overrides base engine.',
    },
    'Ryland Environmental': {
        'has_account': False,
        'format': None,
        'examples': [],
        'extract': lambda x: None,
        'notes': 'Not invoices (receipts/other documents). Overrides base engine.',
    },
    'Interstate Waste': {
        'has_account': False,
        'format': None,
        'examples': [],
        'extract': lambda x: None,
        'notes': 'Not invoices per user review. Overrides base engine.',
    },
    '121 Co Disposal': {
        'has_account': False,
        'format': None,
        'examples': [],
        'extract': lambda x: None,
        'notes': 'Payment receipts, not invoices. No account numbers.',
    },
}
