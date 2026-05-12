"""
Account Extraction Additions - March 2026 v9.3d
Comprehensive vendor patterns from full corpus analysis (233K invoices).

- Helper functions for common extraction patterns
- Improved patterns for top 15 extraction_failed vendors
- ~12 HaulerHero/TrashBilling portal vendors
- 2 NavuSoft portal vendors
- ~120 new vendor patterns (label-based)
- ~150 NO_ACCOUNT vendor overrides
"""
import re
from typing import Optional


# ============================================================
# HELPER FUNCTIONS
# ============================================================

def _expand_labels(labels: list) -> list:
    """Auto-expand label variants so callers don't need to list every form.

    Given labels like ['Account #', 'Customer #'], expands to also include
    'Account No', 'Account Number', 'ACCOUNT NO', 'Customer No', etc.
    """
    # Canonical root words that trigger expansion
    _ACCOUNT_VARIANTS = ['Account #', 'Account No', 'Account Number',
                         'ACCOUNT #', 'ACCOUNT NO', 'ACCOUNT NUMBER',
                         'Acct #', 'Acct No', 'Account Summary']
    _CUSTOMER_VARIANTS = ['Customer #', 'Customer No', 'Customer Number',
                          'CUSTOMER #', 'CUSTOMER NO', 'CUSTOMER NUMBER',
                          'Cust #', 'Cust No', 'Customer ID', 'Cust ID']

    expanded = list(labels)  # preserve originals first
    labels_lower = {l.lower() for l in labels}

    # Check if any label is an account-type label
    has_account = any(l.lower().startswith(('account', 'acct')) for l in labels)
    has_customer = any(l.lower().startswith(('customer', 'cust')) for l in labels)

    if has_account:
        for variant in _ACCOUNT_VARIANTS:
            if variant.lower() not in labels_lower:
                expanded.append(variant)
    if has_customer:
        for variant in _CUSTOMER_VARIANTS:
            if variant.lower() not in labels_lower:
                expanded.append(variant)

    return expanded


def _extract_by_label(text: str, labels: list, value_pattern: str,
                      max_lines: int = 8, backward: bool = False) -> Optional[str]:
    """Generic account extraction by label + value pattern.

    Normalizes literal \\n, searches inline then multi-line (forward and
    optionally backward from label).  Labels are auto-expanded to include
    common variants (Account #/No/Number, Customer #/No/Number, etc.).

    Args:
        labels: Label strings to search for (case-insensitive)
        value_pattern: Regex with one capture group for the value
        max_lines: Max lines to search after/before label
        backward: Also search backward from label (two-column layouts)
    """
    normalized = text.replace('\\n', '\n')
    all_labels = _expand_labels(labels)

    # Inline match: label followed by separator then value
    for label in all_labels:
        # Build flexible label regex (allow whitespace between words)
        words = label.split()
        label_re = r'\s*'.join(re.escape(w) for w in words)
        pat = label_re + r'[:\s#.]*?\s*' + value_pattern
        m = re.search(pat, normalized, re.I)
        if m:
            return m.group(1).strip()

    # Multi-line match
    lines = normalized.split('\n')
    for label in all_labels:
        label_low = label.lower()
        for i, line in enumerate(lines):
            if label_low not in line.lower():
                continue
            # Search forward
            for j in range(i + 1, min(i + max_lines + 1, len(lines))):
                val = lines[j].strip()
                if not val:
                    continue
                m = re.match(value_pattern + r'(?:\s|$)', val, re.I)
                if m:
                    return m.group(1).strip()
            # Search backward (two-column layouts: value before label)
            if backward:
                for j in range(i - 1, max(i - max_lines - 1, -1), -1):
                    val = lines[j].strip()
                    if not val:
                        continue
                    m = re.match(value_pattern + r'(?:\s|$)', val, re.I)
                    if m:
                        return m.group(1).strip()

    return None


def _make_label_extractor(labels: list, value_pattern: str,
                          max_lines: int = 12, backward: bool = False):
    """Factory: returns a callable extractor for the given label/pattern config."""
    def _extract(text: str) -> Optional[str]:
        return _extract_by_label(text, labels, value_pattern, max_lines, backward)
    return _extract


def _extract_hauler_hero_id(text: str) -> Optional[str]:
    """HaulerHero/TrashBilling portal: ID#: NNNN-NNNNNNNNNNNN (4-12 digits).
    Used by 12+ vendors sharing the TrashBilling portal.
    Some vendors use shorter IDs (e.g. EOMS 5-digit, others 9-12 digit).
    """
    normalized = text.replace('\\n', '\n')
    m = re.search(r'ID\s*#\s*:?\s*(\d{4,12})', normalized, re.I)
    return m.group(1) if m else None


def _extract_payment_portal_account(text: str) -> Optional[str]:
    """Payment portal receipts: 'Your account number with this hauler is NNNNNN'.
    Used by 13+ vendors when paying through online portals.
    """
    normalized = text.replace('\\n', '\n')
    m = re.search(r'Your account number with this hauler is\s+(\d{3,12})', normalized, re.I)
    return m.group(1) if m else None


def _extract_hauler_hero_or_portal(text: str) -> Optional[str]:
    """Combined: try HaulerHero ID# first, then payment portal, then label-based.
    Many vendors use HaulerHero for invoicing but have a separate payment
    portal that uses 'Your account number with this hauler is NNNNNN'.
    Also falls back to generic Account #/Customer # label extraction for
    payment receipts that use these labels.
    """
    return (_extract_hauler_hero_id(text)
            or _extract_payment_portal_account(text)
            or _extract_by_label(text, ['Account #'], r'(\d{4,8})', max_lines=8))


def _extract_waste_pro_v2(text: str) -> Optional[str]:
    """Waste Pro v2 — handles multiple BRT account formats.
    Formats: Z-10, 02-0201795 0, 02-100-52525-00-045904, 2445, 2637.
    """
    normalized = text.replace('\\n', '\n')
    # BRT format: NN-NNNNNNN N (with space-separated check digit)
    m = re.search(r'ACCOUNT\s*NUMBER\s*:?\s*\n?\s*(\d{2}-\d{7}\s*\d)', normalized, re.I)
    if m:
        return m.group(1).strip()
    # Long format: NN-NNN-NNNNN-NN-NNNNNN
    m = re.search(r'Account\s*(?:Number|#|No)\s*:?\s*\n?\s*(\d{2}-\d{3}-\d{5}-\d{2}-\d{6})', normalized, re.I)
    if m:
        return m.group(1)
    # Alpha-prefix: Z-10, A-5
    m = re.search(r'Account\s*(?:Number|#|No)\s*:?\s*\n?\s*([A-Z]-?\d{1,4})', normalized, re.I)
    if m:
        return m.group(1)
    # Short numeric: ACCOUNT # → 2445
    return _extract_by_label(text, ['Account #', 'Account Number', 'Customer #'],
                             r'(\d{3,7})', max_lines=8)


def _extract_wm_national_account(text: str) -> Optional[str]:
    """WM National Account format — VENDOR ACCOUNT NUMBER → WGY-code or NN-NNNNNN.
    Column layout: VENDOR ACCOUNT NUMBER label on one line, WGY code 15-20 lines later.
    Also handles: ACCT #: NNNNN, Account Number: NNNNN, Customer ID: NN-NNNNN-NNNNN.
    """
    normalized = text.replace('\\n', '\n')
    # WM Customer ID: 25-34374-43006 format (may have Customer Name between label and value)
    m = re.search(r'Customer\s*ID\s*:?\s*\n?\s*(\d{2}-\d{5}-\d{5})', normalized, re.I)
    if m:
        return m.group(1)
    # Multi-line: Customer ID → skip non-value lines → NN-NNNNN-NNNNN
    lines = normalized.split('\n')
    for i, line in enumerate(lines):
        if re.search(r'Customer\s*ID', line, re.I):
            for j in range(i + 1, min(i + 5, len(lines))):
                val = lines[j].strip()
                m2 = re.match(r'^(\d{2}-\d{5}-\d{5})$', val)
                if m2:
                    return m2.group(1)
    # WGY code (WM vendor account): WGY20070UP, WGY40213AA, WGY 63026AA (with space)
    m = re.search(r'(WGY\s*[A-Z0-9]{5,10})', normalized)
    if m:
        return m.group(1).replace(' ', '')  # Strip internal whitespace
    # ACCT #: NNNNN (small WM subsidiary invoices)
    m = re.search(r'ACCT\s*#\s*:?\s*(\d{4,8})', normalized, re.I)
    if m:
        return m.group(1)
    # Account Number: NNNNN (standard format)
    m = re.search(r'Account\s*Number\s*:?\s*(\d{4,10})', normalized, re.I)
    if m:
        return m.group(1)
    # VENDOR ACCOUNT NUMBER → multi-line scan for NN-NNNNNN format
    lines = normalized.split('\n')
    for i, line in enumerate(lines):
        if 'VENDOR ACCOUNT NUMBER' in line.upper():
            for j in range(i + 1, min(i + 25, len(lines))):
                val = lines[j].strip()
                m2 = re.match(r'^(\d{2,3}-\d{5,8})\s', val)
                if m2:
                    return m2.group(1)
    return None


def _extract_navusoft_account(text: str) -> Optional[str]:
    """NavuSoft portal: ACCOUNT # in column header block.
    Values may appear before or after the labels block.
    Used by: Anytime Waste, Delta Waste, and others using navusoft.net portals.
    """
    normalized = text.replace('\\n', '\n')
    lines = normalized.split('\n')

    for i, line in enumerate(lines):
        if not re.match(r'\s*ACCOUNT\s*#\s*$', line.strip(), re.I):
            continue
        # Search forward for standalone 3-6 digit number
        for j in range(i + 1, min(i + 12, len(lines))):
            val = lines[j].strip()
            if re.match(r'^\d{3,6}$', val):
                return val
        # Search backward for standalone 3-6 digit number
        for j in range(i - 1, max(i - 10, -1), -1):
            val = lines[j].strip()
            if re.match(r'^\d{3,6}$', val):
                return val

    return None


# ============================================================
# IMPROVED VENDOR FUNCTIONS (top extraction_failed vendors)
# ============================================================

def _extract_wasatch_waste_v2(text: str) -> Optional[str]:
    """Wasatch Waste v2 — handles ACCOUNT NUMBER, ACCOUNT NO., .NNNNN formats.
    Formats:
      1. Customer Account # : NNNNNN
      2. ACCOUNT NO. / ACCOUNT NUMBER + 5-7 digit (inline or next-line)
      3. .NNNNN (period-prefixed, Wasatch County format)
      4. Account # or Acct #
    """
    normalized = text.replace('\\n', '\n')
    # Format 1: Customer Account # : NNNNNN
    m = re.search(r'Customer\s*Account\s*#\s*:?\s*(\d{5,7})', normalized, re.I)
    if m:
        return m.group(1)
    # Format 2: ACCOUNT NO. or ACCOUNT NUMBER + value (inline)
    m = re.search(r'ACCOUNT\s*(?:NO\.?|NUMBER)\s*:?\s*(\d{5,7})', normalized, re.I)
    if m:
        return m.group(1)
    # Format 4: Account # or Acct #
    m = re.search(r'(?:Account|Acct)\s*#:?\s*(\d{5,7})', normalized, re.I)
    if m:
        return m.group(1)
    # Multi-line (includes Format 3: .NNNNN)
    # Wasatch County layout has ~13 lines between label and value
    lines = normalized.split('\n')
    for i, line in enumerate(lines):
        if re.search(r'ACCOUNT\s*(?:NO|NUMBER|Information)|Customer\s*Account', line, re.I):
            for j in range(i + 1, min(i + 18, len(lines))):
                val = lines[j].strip()
                # Period-prefixed: .90063, .80081
                m2 = re.match(r'^\.(\d{5,6})$', val)
                if m2:
                    return m2.group(1)
                # Standard numeric
                if re.match(r'^\d{5,7}$', val):
                    return val
    return None


def _extract_robinson_waste_v3(text: str) -> Optional[str]:
    """Robinson Waste v3 — adds Customer: NNNNNN format.
    Formats:
      1. Customer: NNNNNN (6-digit, from issue tickets and Box Tracker)
      2. Customer ID: XNNNN (alpha + 4-5 digit)
      3. ACCOUNT NO. NNNN-NNNNNN (inline)
      4. NNNNN.NNN or NNNNN-NNN (dotted/dashed)
      5. 4-6 digit before/after ACCOUNT NO. label
    """
    normalized = text.replace('\\n', '\n')

    # Format 1: Customer: NNNNNN
    m = re.search(r'Customer:\s*(\d{5,6})\s', normalized)
    if m:
        return m.group(1)

    # Format 2: Customer ID with alpha + digit (C8767)
    m = re.search(r'Customer\s*ID[:\s]*([A-Z]\d{4,5})', normalized, re.I)
    if m:
        return m.group(1).upper()

    # Format 3: ACCOUNT NO. inline
    m = re.search(r'ACCOUNT\s*NO\.?\s*(\d{4,6})\b', normalized, re.I)
    if m:
        return m.group(1)

    lines = normalized.split('\n')

    # Multi-line Customer ID
    for i, line in enumerate(lines[:25]):
        if re.search(r'Customer\s*ID', line, re.I):
            for j in range(i + 1, min(i + 6, len(lines))):
                val = lines[j].strip()
                if re.match(r'^[A-Z]\d{4,5}$', val, re.I):
                    return val.upper()

    # Format 4: NNNNN.NNN or NNNNN-NNN
    for line in lines[:25]:
        m = re.search(r'\b(\d{5}[\.\-]\d{1,3})\b', line)
        if m:
            return m.group(1)

    # Format 5: Value before/after ACCOUNT NO. label
    for i, line in enumerate(lines[:20]):
        if 'ACCOUNT NO' in line.upper():
            for j in range(max(0, i - 6), i):
                val = lines[j].strip()
                if re.match(r'^\d{4,6}$', val):
                    return val
            for j in range(i + 1, min(i + 6, len(lines))):
                val = lines[j].strip()
                if re.match(r'^\d{4,6}$', val):
                    return val

    return None


def _extract_burrtec_v2(text: str) -> Optional[str]:
    """Burrtec v2 — extends search range to i+8 for column-header layout.
    Formats:
      1. NN-XX NNNNNN (47-TD 600084) — alphanumeric with prefix
      2. 6-10 digit numeric
    """
    lines = text.replace('\\n', '\n').split('\n')

    for i, line in enumerate(lines):
        if 'account number' in line.lower():
            for j in range(i + 1, min(i + 8, len(lines))):
                val = lines[j].strip()
                # Alphanumeric: NN-XX NNNNNN
                m = re.match(r'^(\d{2}-[A-Z]{1,3}\s*\d{4,8})$', val, re.I)
                if m:
                    return m.group(1)
                # Numeric: 6-10 digit
                if re.match(r'^\d{6,10}$', val):
                    return val

    for i, line in enumerate(lines):
        if 'customer number' in line.lower() or 'customerid' in line.lower().replace(' ', ''):
            for j in range(i + 1, min(i + 8, len(lines))):
                val = lines[j].strip()
                if re.match(r'^\d{5,10}$', val):
                    return val

    # Inline fallback
    normalized = text.replace('\\n', '\n')
    m = re.search(r'Account\s*Number\s*:?\s*(\d{2}-[A-Z]{1,3}\s*\d{4,8})', normalized, re.I)
    if m:
        return m.group(1)
    m = re.search(r'Account\s*Number\s*:?\s*(\d{6,10})', normalized, re.I)
    if m:
        return m.group(1)
    # CustomerID: NNNNNNNNN
    m = re.search(r'CustomerID[:\s]*(\d{5,10})', normalized, re.I)
    if m:
        return m.group(1)

    return None


def _extract_western_elite_v2(text: str) -> Optional[str]:
    """Western Elite v2 — normalize \\n + multi-line + backward search.
    Formats:
      1. Account Number NNNNNNNN (8-digit, column header layout — value BEFORE label)
      2. Account No NNNNNNNN (transaction receipt format)
      3. Site Act Nbr: NNNNNNNN (inline in service detail section)
      4. Account Summary followed by value on next line
    """
    normalized = text.replace('\\n', '\n')

    # Inline: Account Number/No followed by digits
    m = re.search(r'Account\s*(?:Number|No\.?)\s*:?\s*(\d{7,10})', normalized, re.I)
    if m:
        return m.group(1)

    # Inline: Site Act Nbr: NNNNNNNN
    m = re.search(r'Site\s*Act\s*Nbr\s*:?\s*(\d{7,10})', normalized, re.I)
    if m:
        return m.group(1)

    # Multi-line: search forward AND backward from Account Number/Summary labels
    lines = normalized.split('\n')
    for i, line in enumerate(lines):
        if re.search(r'Account\s*(?:Number|No|Summary)', line, re.I):
            # Forward
            for j in range(i + 1, min(i + 12, len(lines))):
                val = lines[j].strip()
                if re.match(r'^\d{7,10}$', val):
                    return val
            # Backward (columnar header: value before label)
            for j in range(i - 1, max(i - 6, -1), -1):
                val = lines[j].strip()
                if re.match(r'^\d{7,10}$', val):
                    return val

    return None


def _extract_gfl_v3(text: str) -> Optional[str]:
    """GFL v3 — adds XX-NNNN and XN-NNNNN dash formats.
    Formats:
      1. XX-NNNN (alpha-dash-digits: VM-1372, AF-93337)
      2. XN-NNNNN (alpha+digit-dash-digits: A7-87763)
      3. XXNNNNN (alpha+digits: KZ5645, AJ046815)
      4. NNNNNNNNN (7-9 digit numeric)
      5. NNNN (3-5 digit numeric: 2571, 3232)
    """
    normalized = text.replace('\\n', '\n')
    acct_re = r'[A-Z]{1,2}-?\d{3,8}|[A-Z]\d-\d{4,6}|\d{7,9}|\d{3,5}'

    # Inline: CUSTOMER NO. / ACCOUNT NO. / ACCOUNT #
    m = re.search(
        r'(?:CUSTOMER|ACCOUNT)\s*(?:NO\.?|NUMBER|#)\s*:?\s*(' + acct_re + r')',
        normalized, re.I,
    )
    if m:
        return m.group(1).upper()

    # Multi-line forward + backward
    lines = normalized.split('\n')
    for i, line in enumerate(lines):
        if re.search(r'(?:CUSTOMER|ACCOUNT)\s*(?:#|NUMBER|NO)', line, re.I):
            for j in range(i + 1, min(i + 8, len(lines))):
                val = lines[j].strip()
                m2 = re.match(r'^(' + acct_re + r')$', val, re.I)
                if m2:
                    return m2.group(1).upper()
            for j in range(max(0, i - 5), i):
                val = lines[j].strip()
                m2 = re.match(r'^(' + acct_re + r')$', val, re.I)
                if m2:
                    return m2.group(1).upper()

    return None


def _extract_tower_compactor_v2(text: str) -> Optional[str]:
    """Tower Compactor v2 — extends next-line search to 6 lines.
    Format: alpha-prefix Customer ID (HEA003, COCO02, WASOOR).
    """
    normalized = text.replace('\\n', '\n')
    # Inline
    m = re.search(r'Customer\s*ID\s*:?\s*([A-Z][A-Z0-9]{2,7})', normalized, re.I)
    if m:
        return m.group(1).upper()
    # Multi-line
    lines = normalized.split('\n')
    for i, line in enumerate(lines):
        if 'Customer ID' in line:
            for j in range(i + 1, min(i + 6, len(lines))):
                val = lines[j].strip()
                if re.match(r'^[A-Z][A-Z0-9]{2,7}$', val, re.I):
                    return val.upper()
    return None


def _extract_capital_waste_v2(text: str) -> Optional[str]:
    """Capital Waste v2 — adds CUSTOMER NO. label + broadens to 4-6 digits.
    Labels: CUSTOMER NO., CUSTOMER NUMBER, ACCOUNT.
    """
    normalized = text.replace('\\n', '\n')
    lines = normalized.split('\n')

    # Multi-line: search ±8 lines from label
    for i, line in enumerate(lines):
        upper = line.upper().strip()
        if ('CUSTOMER NO' in upper or 'CUSTOMER NUMBER' in upper
                or 'ACCOUNT NO' in upper or 'ACCOUNT NUMBER' in upper
                or upper == 'ACCOUNT'):
            for j in range(max(0, i - 5), min(i + 12, len(lines))):
                val = lines[j].strip()
                if re.match(r'^\d{4,8}$', val):
                    return val

    # Inline
    m = re.search(
        r'(?:CUSTOMER\s*(?:NO\.?|NUMBER)|ACCOUNT\s*(?:NO\.?|NUMBER)?)[:\s]*(\d{4,8})',
        normalized, re.I,
    )
    if m:
        return m.group(1)

    return None


def _extract_rumpke_v3(text: str) -> Optional[str]:
    """Rumpke v3 — broadens to 8-10 digits, handles 'N NNNNNNNN' format.
    Labels: Customer #, Cust #, Account #, CUSTOMER NUMBER.
    """
    normalized = text.replace('\\n', '\n')

    # Inline: Customer # 01020764 or Account # 0201169794
    m = re.search(r'(?:Account|Customer|Cust)\s*#:?\s*(\d{8,10})', normalized, re.I)
    if m:
        return m.group(1)

    # Multi-line
    lines = normalized.split('\n')
    for i, line in enumerate(lines):
        if re.search(r'(?:Account|Customer|Cust)\s*(?:#|Number)', line, re.I):
            for j in range(i + 1, min(i + 6, len(lines))):
                val = lines[j].strip()
                # Standard 8-10 digit
                if re.match(r'^\d{8,10}$', val):
                    return val
                # Format: N NNNNNNNN (page prefix + account)
                m2 = re.match(r'^\d\s+(\d{8,10})$', val)
                if m2:
                    return m2.group(1)

    # CUSTOMER NUMBER then value
    m = re.search(r'CUSTOMER\s*NUMBER\s*\n\s*(\d{8,10})', normalized, re.I)
    if m:
        return m.group(1)

    # ACCESS CODE fallback (Rumpke invoices where CUST # value is garbled)
    for i, line in enumerate(lines):
        if 'access code' in line.lower():
            for j in range(max(0, i - 3), min(i + 3, len(lines))):
                val = lines[j].strip()
                if re.match(r'^\d{8,12}$', val):
                    return val

    return None


def _extract_live_oak_v2(text: str) -> Optional[str]:
    """Live Oak v2 — handles Acct# inline, Account #, and CUSTOMER NO formats.
    Formats: 170369 (6-digit), 04-0039379 (NN-NNNNNNN).
    """
    normalized = text.replace('\\n', '\n')
    # Inline: Acct# 170369 or Acct #: 170369
    m = re.search(r'Acct\s*#\s*:?\s*(\d{6})', normalized, re.I)
    if m:
        return m.group(1)
    # Inline: CUSTOMER NO 170369
    m = re.search(r'CUSTOMER\s*NO\.?\s*:?\s*(\d{6})', normalized, re.I)
    if m:
        return m.group(1)
    # Label-based (Account #, Customer #) with NN-NNNNNNN or NNNNNN
    return (_extract_by_label(text, ['Account #', 'Acct #'], r'(\d{6})', max_lines=6)
            or _extract_by_label(text, ['Account #', 'Customer #'], r'(\d{2}-\d{5,8})', max_lines=8))


def _extract_walker_lake_v2(text: str) -> Optional[str]:
    """Walker Lake Disposal v2 — normalize \\n + multi-line search.
    Format: 3-6 digit numeric after Account #.
    """
    normalized = text.replace('\\n', '\n')
    m = re.search(r'Account\s*#\s*:?\s*(\d{3,6})', normalized, re.I)
    if m:
        return m.group(1)
    lines = normalized.split('\n')
    for i, line in enumerate(lines):
        if re.search(r'Account\s*#', line, re.I):
            for j in range(i + 1, min(i + 5, len(lines))):
                val = lines[j].strip()
                if re.match(r'^\d{3,6}$', val):
                    return val
    return None


def _extract_fcc_environmental_v2(text: str) -> Optional[str]:
    """FCC Environmental v2 — Customer ID in column-header layout.
    Formats:
      1. Customer ID: XXXNNNN (PSL1078, FL1177, TS00148524) — 2-4 alpha + 3-8 digits
      2. Customer ID: XXX-NNNN-N (PBC-3453-5) — dash-separated
      3. ACCOUNT # (4-6 digit) — Houston subsidiary
    Column layout: Customer ID: label is followed by other field labels before value.
    """
    normalized = text.replace('\\n', '\n')
    # FCC Customer ID pattern: alpha prefix (2-4 chars) + optional dashes + digits
    cid_re = r'[A-Z]{2,4}[-]?\d{3,8}[-]?\d{0,2}'

    # Inline Customer ID
    m = re.search(r'Customer\s*ID[:\s]*(' + cid_re + r')', normalized, re.I)
    if m:
        return m.group(1).upper()

    # Inline ACCOUNT #
    m = re.search(r'ACCOUNT\s*#[:\s]*(\d{4,6})', normalized, re.I)
    if m:
        return m.group(1)

    # Multi-line forward + backward
    lines = normalized.split('\n')
    for i, line in enumerate(lines):
        if re.search(r'Customer\s*ID', line, re.I):
            for j in range(i + 1, min(i + 12, len(lines))):
                val = lines[j].strip()
                if re.match(r'^' + cid_re + r'$', val, re.I):
                    return val.upper()
            for j in range(max(0, i - 8), i):
                val = lines[j].strip()
                if re.match(r'^' + cid_re + r'$', val, re.I):
                    return val.upper()
        if re.search(r'ACCOUNT\s*#', line, re.I):
            for j in range(i + 1, min(i + 8, len(lines))):
                val = lines[j].strip()
                if re.match(r'^\d{4,6}$', val):
                    return val

    return None


def _extract_lrs_account(text: str) -> Optional[str]:
    """LRS — Customer No / Account No in column-header or inline layout.
    Formats: 4-7 digit numeric, or NN-NNNNNNN (dash format with optional check digit).
    Column headers: Invoice No, Page No, Invoice Date, Customer No, Site No, Reference
    Values follow as a block: UA37557, 1 of 1, Dec-31-24, 37512, 0, ...
    Also: Account No. 08-8167910 (BRT inline format).
    """
    normalized = text.replace('\\n', '\n')
    # Inline: Account No. 08-8167910 or Account No. 08-816792 8
    m = re.search(r'Account\s*No\.?\s*:?\s*(\d{2}-\d{6,8}(?:\s*\d)?)', normalized, re.I)
    if m:
        return m.group(1).strip()
    # Inline: Customer No: 37512 or Customer No 37512
    m = re.search(r'Customer\s*No\.?\s*:?\s*(\d{4,7})', normalized, re.I)
    if m:
        return m.group(1)
    # Multi-line column-header layout — need wide search range
    lines = normalized.split('\n')
    for i, line in enumerate(lines):
        if re.search(r'(?:Customer|Account)\s*No\b', line, re.I):
            for j in range(i + 1, min(i + 12, len(lines))):
                val = lines[j].strip()
                # BRT format: NN-NNNNNNN or NN-NNNNNNN N
                m2 = re.match(r'^(\d{2}-\d{6,8}(?:\s*\d)?)$', val)
                if m2:
                    return m2.group(1).strip()
                # Exact 4-7 digit
                if re.match(r'^\d{4,7}$', val):
                    return val
                # NNNN.NN format (customer.site) — extract part before period
                m2 = re.match(r'^(\d{4,7})\.\d{1,3}$', val)
                if m2:
                    return m2.group(1)
    return None


def _extract_miami_dade_dswm(text: str) -> Optional[str]:
    """Miami-Dade DSWM — multiple formats:
    - Panzarella: Account No. NN-NNNN N (01-4649 9)
    - Great Waste (misdetected): Account Number → NNNNNNN (7 digit)
    - General: Account Number → 5-10 digit numeric
    """
    normalized = text.replace('\\n', '\n')
    # NN-NNNN N format (01-4649 9)
    m = re.search(r'Account\s*No\.?\s*:?\s*(\d{2}-\d{4}\s*\d)', normalized, re.I)
    if m:
        return m.group(1).strip()
    # Multi-line: Account Number → 5-10 digit
    lines = normalized.split('\n')
    for i, line in enumerate(lines):
        if re.search(r'Account\s*(?:Number|No)', line, re.I):
            for j in range(i + 1, min(i + 8, len(lines))):
                val = lines[j].strip()
                # NN-NNNN N format
                m2 = re.match(r'^(\d{2}-\d{4}\s*\d)', val)
                if m2:
                    return m2.group(1).strip()
                # 5-10 digit numeric (Great Waste, etc.)
                if re.match(r'^\d{5,10}$', val):
                    return val
    return None


# ============================================================
# VENDOR DICT
# ============================================================

VENDOR_ADDITIONS_MAR2026_V93D = {

    # ----------------------------------------------------------
    # IMPROVED PATTERNS (override existing entries)
    # ----------------------------------------------------------

    'Wasatch Waste': {
        'has_account': True,
        'format': 'NNNNNN or .NNNNN',
        'examples': ['000083', '90063'],
        'extract': _extract_wasatch_waste_v2,
    },

    'Robinson Waste': {
        'has_account': True,
        'format': 'NNNNNN or XNNNN or NNNNN.NNN',
        'examples': ['055779', 'C8767', '51001'],
        'extract': _extract_robinson_waste_v3,
    },

    'Burrtec': {
        'has_account': True,
        'format': 'NN-XX NNNNNN or NNNNNNNN',
        'examples': ['47-TD 600084', '15063480'],
        'extract': _extract_burrtec_v2,
    },

    'Western Elite': {
        'has_account': True,
        'format': 'NNNNNNNN (8-digit)',
        'examples': ['12030802', '12030805'],
        'extract': _extract_western_elite_v2,
    },

    'GFL': {
        'has_account': True,
        'format': 'XX-NNNN or XXNNNNN or NNNNNNNNN',
        'examples': ['VM-1372', 'AF-93337', 'KZ5645'],
        'extract': _extract_gfl_v3,
    },

    'Tower Compactor': {
        'has_account': True,
        'format': 'XXXNNN (alpha-prefix)',
        'examples': ['HEA003', 'COCO02'],
        'extract': _extract_tower_compactor_v2,
    },

    'Capital Waste': {
        'has_account': True,
        'format': 'NNNNN (4-8 digit)',
        'examples': ['52294', '44587'],
        'extract': _extract_capital_waste_v2,
    },

    'Rumpke': {
        'has_account': True,
        'format': 'NNNNNNNN (8-10 digit)',
        'examples': ['01020764', '0201169794'],
        'extract': _extract_rumpke_v3,
    },

    'Walker Lake Disposal': {
        'has_account': True,
        'format': 'NNN-NNNNNN (3-6 digit)',
        'examples': ['375'],
        'extract': _extract_walker_lake_v2,
    },

    'FCC Environmental': {
        'has_account': True,
        'format': 'XXNNNNNNNN or NNNNN',
        'examples': ['TS00148524', '25489'],
        'extract': _extract_fcc_environmental_v2,
    },

    'LRS': {
        'has_account': True,
        'format': 'NNNNNN (5-7 digit)',
        'examples': ['208373'],
        'extract': _extract_lrs_account,
    },

    'Miami-Dade DSWM': {
        'has_account': True,
        'format': 'NN-NNNN N',
        'examples': ['01-4649 9'],
        'extract': _extract_miami_dade_dswm,
    },

    # ----------------------------------------------------------
    # HAULER HERO / TRASHBILLING PORTAL VENDORS
    # All use ID#: NNNNNNNNNNNN (9-12 digit)
    # ----------------------------------------------------------

    'Liberty Disposal': {
        'has_account': True,
        'format': 'HaulerHero 12-digit ID#',
        'examples': ['660090017655'],
        'extract': _extract_hauler_hero_or_portal,
    },
    'AT Disposal': {
        'has_account': True,
        'format': 'HaulerHero 12-digit ID#',
        'examples': ['123700007393'],
        'extract': _extract_hauler_hero_or_portal,
    },
    'American Disposal': {
        'has_account': True,
        'format': 'HaulerHero 12-digit ID#',
        'examples': ['105660076400'],
        'extract': _extract_hauler_hero_or_portal,
    },
    'Idaho Falls Utilities': {
        'has_account': True,
        'format': 'HaulerHero 12-digit ID#',
        'examples': ['101530116501'],
        'extract': _extract_hauler_hero_or_portal,
    },
    "Cockey's Enterprises": {
        'has_account': True,
        'format': 'HaulerHero 12-digit ID#',
        'examples': ['125530001395'],
        'extract': _extract_hauler_hero_or_portal,
    },
    'Tostenson, Inc': {
        'has_account': True,
        'format': 'HaulerHero 12-digit ID#',
        'examples': ['108310008838'],
        'extract': _extract_hauler_hero_or_portal,
    },
    'City Sanitary Service': {
        'has_account': True,
        'format': 'HaulerHero 12-digit ID#',
        'examples': ['120720005176'],
        'extract': _extract_hauler_hero_or_portal,
    },
    'Stanphill Sanitation, LLC.': {
        'has_account': True,
        'format': 'HaulerHero 12-digit ID#',
        'examples': ['717210026347'],
        'extract': _extract_hauler_hero_or_portal,
    },
    'SSW-Box Services': {
        'has_account': True,
        'format': 'HaulerHero 12-digit ID#',
        'examples': ['585660059900'],
        'extract': _extract_hauler_hero_or_portal,
    },
    'PRYOR WASTE & RECYCLING LLC': {
        'has_account': True,
        'format': 'HaulerHero 12-digit ID#',
        'examples': ['408060241940'],
        'extract': _extract_hauler_hero_or_portal,
    },
    'Temps Disposal Service': {
        'has_account': True,
        'format': 'HaulerHero 12-digit ID#',
        'examples': ['568010097444'],
        'extract': _extract_hauler_hero_or_portal,
    },
    'Tri-County Waste of Henderson': {
        'has_account': True,
        'format': 'HaulerHero 12-digit ID#',
        'examples': ['102000014518'],
        'extract': _extract_hauler_hero_or_portal,
    },
    'K & K Sanitation': {
        'has_account': True,
        'format': 'HaulerHero payment receipt Account #',
        'examples': ['120333'],
        'extract': lambda text: (
            _extract_hauler_hero_or_portal(text)
            or _extract_by_label(text, ['Account #'], r'(\d{4,7})', max_lines=8)
        ),
    },
    'Midwest Disposal IL': {
        'has_account': True,
        'format': 'HaulerHero payment receipt Account #',
        'examples': ['107512'],
        'extract': _extract_hauler_hero_or_portal,
    },
    'Davis Disposal': {
        'has_account': True,
        'format': 'HaulerHero payment receipt Account #',
        'examples': ['11941'],
        'extract': _extract_hauler_hero_or_portal,
    },
    'Blue Hills Environmental': {
        'has_account': True,
        'format': 'HaulerHero payment receipt Account #',
        'examples': ['112835'],
        'extract': _extract_hauler_hero_or_portal,
    },
    'Shamrock Waste': {
        'has_account': True,
        'format': 'HaulerHero payment receipt Account #',
        'examples': ['100023'],
        'extract': _extract_hauler_hero_or_portal,
    },

    # ----------------------------------------------------------
    # NAVUSOFT PORTAL VENDORS
    # ACCOUNT # in column header block
    # ----------------------------------------------------------

    'Anytime Waste': {
        'has_account': True,
        'format': 'NavuSoft ACCOUNT # or WM VENDOR ACCOUNT NUMBER',
        'examples': ['24496', 'WGY20070UP'],
        'extract': lambda text: (_extract_navusoft_account(text)
                                 or _extract_wm_national_account(text)),
    },
    'Delta Waste': {
        'has_account': True,
        'format': 'NavuSoft ACCOUNT # (4 digit)',
        'examples': ['1014'],
        'extract': _extract_navusoft_account,
    },

    # ----------------------------------------------------------
    # NEW VENDOR PATTERNS (label-based extraction)
    # Organized by tier (highest failure count first)
    # ----------------------------------------------------------

    # --- Tier 1-2 (40+ failures) ---

    'Cards Recycling': {
        'has_account': True,
        'format': 'NN-NNNN (Account No.) or NavuSoft ACCOUNT # (4-5 digit)',
        'examples': ['20-5678', '71858'],
        'extract': lambda text: (
            _extract_by_label(text, ['Account No', 'Account #', 'Customer No'],
                              r'(\d{2}-\d{4,5})')
            or _extract_navusoft_account(text)
        ),
    },
    'Mt Diablo Resource Recovery': {
        'has_account': True,
        'format': 'NN-NNNNNNN (01-107464)',
        'examples': ['01-107464', '01-0112788'],
        'extract': _make_label_extractor(
            ['Customer #', 'ACCOUNT NUMBER', 'Account Number', 'Account #'],
            r'(\d{2}-\d{5,7})'),
    },
    'West Oahu Aggregate': {
        'has_account': True,
        'format': 'NNNNNNNN (8 digit)',
        'examples': ['12345678'],
        'extract': _make_label_extractor(
            ['Account #', 'Account Number', 'Customer #'], r'(\d{6,9})'),
    },
    'City of Tacoma': {
        'has_account': True,
        'format': 'NNNNNNNNNN (10 digit)',
        'examples': ['1098322802', '1098019001'],
        'extract': _make_label_extractor(
            ['Customer #', 'Account #', 'Account Number'], r'(\d{9,11})'),
    },
    'MARS City of Beatrice': {
        'has_account': True,
        'format': 'NNNN (4-5 digit)',
        'examples': ['6704', '6705'],
        'extract': _make_label_extractor(
            ['CUSTOMER NO', 'Customer No', 'Customer #', 'Account #'], r'(\d{3,5})'),
    },
    'Mountain State Waste': {
        'has_account': True,
        'format': 'NNNNN or NNNNNNNNN',
        'examples': ['70953', '70953001'],
        'extract': _make_label_extractor(
            ['Account #', 'Site #', 'Customer #'], r'(\d{4,9})'),
    },
    'Cleeton Sanitation': {
        'has_account': True,
        'format': 'NNNNNN (6 digit)',
        'examples': ['443946', '443947'],
        'extract': _make_label_extractor(
            ['Account Number', 'Account #', 'Customer #'], r'(\d{5,7})'),
    },
    'Goode Companies': {
        'has_account': True,
        'format': 'NNNNNN (6 digit)',
        'examples': ['800851'],
        'extract': _make_label_extractor(
            ['Account #', 'Customer #'], r'(\d{5,7})'),
    },
    'LaVeine Sanitation': {
        'has_account': True,
        'format': 'NN-NNNNN',
        'examples': ['01-987', '01-13572'],
        'extract': _make_label_extractor(
            ['Account No', 'Account #', 'Customer #'], r'(\d{2}-\d{3,6})'),
    },
    'City of Tucson': {
        'has_account': True,
        'format': 'NNNNNNN-NNNN(N)',
        'examples': ['1679429-1236'],
        'extract': _make_label_extractor(
            ['Account #', 'Account Number'], r'(\d{5,8}-\d{3,6})'),
    },
    'E.J. Harrison & Sons': {
        'has_account': True,
        'format': 'N -NNNNNNN (space before dash in OCR)',
        'examples': ['1 -0240236', '1 -0240221'],
        'extract': _make_label_extractor(
            ['ACCOUNT #', 'Account #'], r'(\d{1,2}\s*-\d{5,8})'),
    },
    'MID-NEBRASKA DISPOSAL, INC': {
        'has_account': True,
        'format': 'NNNNN (5 digit)',
        'examples': ['81884'],
        'extract': _make_label_extractor(
            ['Account No', 'Account #', 'Customer #'], r'(\d{4,6})'),
    },

    # --- Additional Tier 1-2 vendors (from detailed OCR analysis) ---

    'California Waste Recovery': {
        'has_account': True,
        'format': 'NN-NNNNN (01-42903)',
        'examples': ['01-42903'],
        'extract': _make_label_extractor(
            ['Account No', 'Account #'], r'(\d{2}-\d{4,6})'),
    },
    'Midwest Sanitation': {
        'has_account': True,
        'format': 'NNNNNNN (7 digit)',
        'examples': ['3931900', '3549500'],
        'extract': _make_label_extractor(
            ['Account Number', 'ActNbr', 'Account #'], r'(\d{7})'),
    },
    'Universal Waste': {
        'has_account': True,
        'format': 'NNNNNN (6 digit)',
        'examples': ['273586', '273238'],
        'extract': _make_label_extractor(
            ['Customer Number', 'Customer #'], r'(\d{6})'),
    },
    'Arrowaste': {
        'has_account': True,
        'format': 'NN-NNNNN (91-99544)',
        'examples': ['91-99544', '91-226107'],
        'extract': _make_label_extractor(
            ['Customer #', 'Account #'], r'(\d{2}-\d{5,6})'),
    },
    'City of Oakland Park': {
        'has_account': True,
        'format': 'NNNNNNNNNN (10 digit)',
        'examples': ['1098322802'],
        'extract': _make_label_extractor(
            ['Account Number', 'Account No'], r'(\d{10})'),
    },
    'F & L Construction': {
        'has_account': True,
        'format': 'NNNN (4-5 digit)',
        'examples': ['2105', '2310'],
        'extract': _make_label_extractor(
            ['CUSTOMER NO', 'Customer No', 'Customer #'], r'(\d{4,5})'),
    },
    'Best Way Disposal': {
        'has_account': True,
        'format': 'NNNNNN (6-9 digit)',
        'examples': ['491900', '161766100'],
        'extract': _make_label_extractor(
            ['Account Number', 'Account#', 'Account #'], r'(\d{6,9})'),
    },
    'Casella': {
        'has_account': True,
        'format': 'NNNNNN (5-6 digit) or ACCOUNT NUMBER (4-6 digit) or HaulerHero ID#',
        'examples': ['350362', '10206', '125530001395'],
        'extract': lambda text: (
            _extract_by_label(text,
                ['CUSTOMER #', 'Customer #', 'ACCOUNT NUMBER', 'Account Number', 'Account #'],
                r'(\d{4,6})')
            or _extract_hauler_hero_or_portal(text)
        ),
    },
    'Recycling Services of Florida': {
        'has_account': True,
        'format': 'NNNN (4-5 digit) or WASXXX',
        'examples': ['2878', 'WAS333'],
        'extract': _make_label_extractor(
            ['CUSTOMER NO', 'Customer No', 'Customer'], r'(\d{4,5}|WAS\d{3})'),
    },

    # --- Tier 3 (25-39 failures) ---

    'Coastal Waste': {
        'has_account': True,
        'format': 'NNNNNN-NNN-NNN',
        'examples': ['013555-024-002'],
        'extract': _make_label_extractor(
            ['Account #', 'Customer #'], r'(\d{5,7}-\d{3}-\d{3})'),
    },
    'Thompson Sanitation': {
        'has_account': True,
        'format': 'COMNNNNNN (alpha-prefix)',
        'examples': ['COM001751'],
        'extract': _make_label_extractor(
            ['ACCOUNT NO', 'Account No', 'Account #', 'Customer #'],
            r'([A-Z]{2,4}\d{4,8})'),
    },
    'City of Mesquite': {
        'has_account': True,
        'format': 'NNNNNN (6 digit)',
        'examples': ['669900'],
        'extract': _make_label_extractor(
            ['Account #', 'Customer #'], r'(\d{5,7})'),
    },
    'Glendale Arizona Utilities': {
        'has_account': True,
        'format': 'NNNNNNNN-NN',
        'examples': ['00327534-00'],
        'extract': _make_label_extractor(
            ['Account #', 'Account Number'], r'(\d{7,9}-\d{2})'),
    },
    'City of Grand Junction': {
        'has_account': True,
        'format': 'NNNNNNNN-NN or NNNN',
        'examples': ['00009042-00', '3310'],
        'extract': _make_label_extractor(
            ['Account Number', 'Customer #', 'Account #'], r'(\d{4,9}(?:-\d{2})?)'),
    },
    'Friedman Recycling': {
        'has_account': True,
        'format': 'NNNNNNNN (8 digit)',
        'examples': ['11668500'],
        'extract': _make_label_extractor(
            ['ACCOUNT #', 'Account #', 'Customer #'], r'(\d{7,9})'),
    },
    'Live Oak': {
        'has_account': True,
        'format': 'NNNNNN or NN-NNNNNNN',
        'examples': ['170369', '04-0039379'],
        'extract': _extract_live_oak_v2,
    },
    'American Recycling': {
        'has_account': True,
        'format': 'NNNNNN (6 digit)',
        'examples': ['119618'],
        'extract': _make_label_extractor(
            ['Account #', 'Customer #'], r'(\d{5,7})'),
    },
    'Cheyenne Board of Public Utilities': {
        'has_account': True,
        'format': 'NNNNNN (6 digit)',
        'examples': ['668376'],
        'extract': _make_label_extractor(
            ['Customer Number', 'Account #'], r'(\d{5,7})'),
    },
    'Modern Disposal': {
        'has_account': True,
        'format': 'NNNNNN or NNNNNNNNNN (+ site suffix)',
        'examples': ['053262', '0532620001'],
        'extract': _make_label_extractor(
            ['Site #', 'Customer #', 'Account #'], r'(\d{5,10})'),
    },
    'Southern Sanitation': {
        'has_account': True,
        'format': 'NNNNNN or NN-NNNNN-NNNNN',
        'examples': ['210917'],
        'extract': _make_label_extractor(
            ['Account No', 'Customer #', 'Account #'],
            r'(\d{5,7}|\d{2}-\d{5}-\d{5})'),
    },
    'Timmons Waste Service': {
        'has_account': True,
        'format': 'NNNNNNNNNNNN (TrashBilling ID#)',
        'examples': ['107780139390', '13939'],
        'extract': _extract_hauler_hero_or_portal,
    },
    'EOMS Recycling': {
        'has_account': True,
        'format': 'NNNNN (TrashBilling ID#, 4-12 digit)',
        'examples': ['14633', '108550126510'],
        'extract': _extract_hauler_hero_or_portal,
    },
    'Wayne County Utah': {
        'has_account': True,
        'format': 'NNN (3 digit)',
        'examples': ['348'],
        'extract': _make_label_extractor(
            ['Customer #', 'Account #'], r'(\d{3,5})'),
    },
    'Community Waste': {
        'has_account': True,
        'format': 'NNNNNN (6 digit)',
        'examples': ['102167'],
        'extract': _make_label_extractor(
            ['Account #', 'Customer #'], r'(\d{5,7})'),
    },
    'Sustainable Environmental Management': {
        'has_account': True,
        'format': 'NNNNNNN or NNNNNNNNN',
        'examples': ['2587600', '895910001'],
        'extract': _make_label_extractor(
            ['Account #', 'Customer #'], r'(\d{6,10})'),
    },
    'City of Foley': {
        'has_account': True,
        'format': 'NN-NNNN',
        'examples': ['01-1589'],
        'extract': _make_label_extractor(
            ['Account #', 'Customer #'], r'(\d{2}-\d{3,5})'),
    },
    'Southwest Sanitation': {
        'has_account': True,
        'format': 'NN-NNNNNN',
        'examples': ['01-212869'],
        'extract': _make_label_extractor(
            ['Account #', 'Customer #'], r'(\d{2}-\d{5,7})'),
    },
    'Texas Disposal': {
        'has_account': True,
        'format': 'N-NNNN or N-NNNNNN',
        'examples': ['9-7551', '1-292299'],
        'extract': _make_label_extractor(
            ['Account #', 'Customer #'], r'(\d{1,2}-\d{4,7})'),
    },
    'Basin Disposal': {
        'has_account': True,
        'format': 'NNNNNN (6 digit)',
        'examples': ['436926'],
        'extract': _make_label_extractor(
            ['Account #', 'Customer #'], r'(\d{5,7})'),
    },
    'Huntsville Hauling': {
        'has_account': True,
        'format': 'NN-NNNNNNN',
        'examples': ['77-1002796'],
        'extract': _make_label_extractor(
            ['Account No', 'Account #', 'Customer #'], r'(\d{2}-\d{5,8})'),
    },
    "Harter's": {
        'has_account': True,
        'format': 'NN-NNNN',
        'examples': ['03-1573'],
        'extract': _make_label_extractor(
            ['Customer #', 'Account #'], r'(\d{2}-\d{3,5})'),
    },
    'Olympic Compactor Rentals': {
        'has_account': True,
        'format': 'NN-NNNNNNN',
        'examples': ['01-0002544'],
        'extract': _make_label_extractor(
            ['Customer #', 'Account #'], r'(\d{2}-\d{5,8})'),
    },
    'Win Waste': {
        'has_account': True,
        'format': 'NN-NNNN-NNNN',
        'examples': ['30-2676-0000'],
        'extract': _make_label_extractor(
            ['Customer #', 'Account #'], r'(\d{2}-\d{4}-\d{4})'),
    },
    'AAA Disposal Service': {
        'has_account': True,
        'format': 'NNNN-NNNNN (4-5 digit)',
        'examples': ['4615', '99957'],
        'extract': _make_label_extractor(
            ['Account #', 'Customer #'], r'(\d{4,6})'),
    },
    'AWS': {
        'has_account': True,
        'format': 'NN-NNNNNN',
        'examples': ['10-354344'],
        'extract': _make_label_extractor(
            ['Customer #', 'Account #'], r'(\d{2}-\d{5,7})'),
    },
    'Disposal Management': {
        'has_account': True,
        'format': 'NNNNNN (6 digit)',
        'examples': ['203913'],
        'extract': _make_label_extractor(
            ['Account #', 'Customer #'], r'(\d{5,7})'),
    },
    'Engebretson & Sons': {
        'has_account': True,
        'format': 'NNNN-NNNNNN or NNNNNNN or ActNbr: NNNNNNN',
        'examples': ['3061-213744', '1043070'],
        'extract': _make_label_extractor(
            ['Account #', 'Customer #', 'ActNbr'],
            r'(\d{4,7}-?\d{0,7})'),
    },
    'Parish Disposal': {
        'has_account': True,
        'format': 'XXNNNNNXX (alpha-prefix)',
        'examples': ['FH5127FL'],
        'extract': _make_label_extractor(
            ['Account #', 'Customer #'], r'([A-Z]{2}\d{4,6}[A-Z]{0,2})'),
    },

    # --- Tier 4 (15-24 failures) ---

    'Elecke': {
        'has_account': True,
        'format': 'NN-NNNNNN',
        'examples': ['01-810926'],
        'extract': _make_label_extractor(
            ['Account #', 'Customer #'], r'(\d{2}-\d{5,7})'),
    },
    'Texas Commercial Waste': {
        'has_account': True,
        'format': 'NN-NNN',
        'examples': ['01-476'],
        'extract': _make_label_extractor(
            ['Customer #', 'Account #'], r'(\d{2}-\d{3,5})'),
    },
    'Checksammy': {
        'has_account': True,
        'format': 'XXXNNNN (alpha-prefix)',
        'examples': ['WST2531'],
        'extract': _make_label_extractor(
            ['Account #', 'Customer #'], r'([A-Z]{2,4}\d{3,6})'),
    },
    'Empire Disposal': {
        'has_account': True,
        'format': 'NNNN-NNNNNNN',
        'examples': ['2120-1152029'],
        'extract': _make_label_extractor(
            ['Account #', 'Customer #'], r'(\d{4}-\d{5,8})'),
    },
    'Tacoma Public Utilities': {
        'has_account': True,
        'format': 'NNNNNNNNN (9 digit)',
        'examples': ['300106553'],
        'extract': _make_label_extractor(
            ['Account #', 'Account Number'], r'(\d{8,10})'),
    },
    'AIKEN REFUSE': {
        'has_account': True,
        'format': 'XX-NNNNNNN (alpha-prefix)',
        'examples': ['FL-2000736'],
        'extract': _make_label_extractor(
            ['Account #', 'Customer #'], r'([A-Z]{2}-\d{5,8})'),
    },
    'Gotta Go Waste': {
        'has_account': True,
        'format': 'NNNNNN (6 digit)',
        'examples': ['107933'],
        'extract': _make_label_extractor(
            ['Cust ID', 'Customer #', 'Account #'], r'(\d{5,7})'),
    },
    'Tahoe Basin Container': {
        'has_account': True,
        'format': 'NNNNNNNN or NN-NNNNN',
        'examples': ['54661000', '50-11144'],
        'extract': _make_label_extractor(
            ['Account #', 'Customer #'],
            r'(\d{7,9}|\d{2}-\d{4,6})'),
    },
    'Talon Sanitation': {
        'has_account': True,
        'format': 'NNNNNN (6 digit)',
        'examples': ['130322'],
        'extract': _make_label_extractor(
            ['Account #', 'Customer #'], r'(\d{5,7})'),
    },
    'Syracuse Haulers': {
        'has_account': True,
        'format': 'NN-NNNNN(N)',
        'examples': ['10-28958'],
        'extract': _make_label_extractor(
            ['Account #', 'Customer #'], r'(\d{2}-\d{4,7})'),
    },
    'City of Emporia': {
        'has_account': True,
        'format': 'NNNNNN or NNNNN',
        'examples': ['370050', '22828'],
        'extract': _make_label_extractor(
            ['Account #', 'Customer #'], r'(\d{4,7})'),
    },
    'Nitti Sanitation': {
        'has_account': True,
        'format': 'NNNNNN (next-line)',
        'examples': ['708233'],
        'extract': _make_label_extractor(
            ['Account Number', 'Account #'], r'(\d{5,8})', max_lines=10),
    },
    'First Piedmont': {
        'has_account': True,
        'format': 'NNNNNNN (7 digit)',
        'examples': ['5038400'],
        'extract': _make_label_extractor(
            ['Account #', 'Customer #'], r'(\d{6,8})'),
    },
    'Florida Express Waste': {
        'has_account': True,
        'format': 'NN-NNNNN',
        'examples': ['01-92630'],
        'extract': _make_label_extractor(
            ['Account #', 'Customer #'], r'(\d{2}-\d{4,6})'),
    },
    'Johns Disposal WI': {
        'has_account': True,
        'format': 'NN-NNNNNNN',
        'examples': ['01-1175313'],
        'extract': _make_label_extractor(
            ['Account #', 'Customer #'], r'(\d{2}-\d{5,8})'),
    },
    'Lincoln County Solid Waste': {
        'has_account': True,
        'format': 'NNNNNN (6 digit)',
        'examples': ['706114'],
        'extract': _make_label_extractor(
            ['Customer #', 'Account #'], r'(\d{5,7})'),
    },
    'Penn Waste': {
        'has_account': True,
        'format': 'XXNNNNNN (alpha-prefix)',
        'examples': ['PC183438'],
        'extract': _make_label_extractor(
            ['Customer #', 'Account #'], r'([A-Z]{2}\d{5,8})'),
    },
    'Western Kane County': {
        'has_account': True,
        'format': 'XNNNN (alpha-prefix)',
        'examples': ['C1223'],
        'extract': _make_label_extractor(
            ['Account #', 'Customer #'], r'([A-Z]\d{3,5})'),
    },
    'Cavossa Disposal': {
        'has_account': True,
        'format': 'XXNNNNNNNN (alpha-prefix)',
        'examples': ['CW00033508'],
        'extract': _make_label_extractor(
            ['Customer #', 'Account #'], r'([A-Z]{2}\d{6,10})'),
    },
    'Great Waste': {
        'has_account': True,
        'format': 'NNNNNNN (7 digit)',
        'examples': ['1190930'],
        'extract': _make_label_extractor(
            ['Account #', 'Customer #'], r'(\d{6,8})'),
    },
    'Grogan Disposal': {
        'has_account': True,
        'format': 'NNNNN (5 digit)',
        'examples': ['11646'],
        'extract': _make_label_extractor(
            ['Account #', 'Customer #'], r'(\d{4,6})'),
    },
    'RES Waste': {
        'has_account': True,
        'format': 'NN-NNNNN',
        'examples': ['01-55912'],
        'extract': _make_label_extractor(
            ['Account #', 'Customer #'], r'(\d{2}-\d{4,6})'),
    },
    'WB Waste Solutions': {
        'has_account': True,
        'format': 'NNNNNNNNN (9 digit + site)',
        'examples': ['150100615'],
        'extract': _make_label_extractor(
            ['Customer #', 'Site #', 'Account #'], r'(\d{7,10})'),
    },
    'A1 INDUSTRIAL MAINTENANCE': {
        'has_account': True,
        'format': 'NNNN (4 digit)',
        'examples': ['7657'],
        'extract': _make_label_extractor(
            ['Account #', 'Customer #'], r'(\d{3,5})'),
    },
    'MA Sanitation': {
        'has_account': True,
        'format': 'NN-NNN',
        'examples': ['10-337'],
        'extract': _make_label_extractor(
            ['Customer #', 'Account #'], r'(\d{2}-\d{3,5})'),
    },
    'MARATHON GARBAGE SERVICE': {
        'has_account': True,
        'format': 'NN-NNN',
        'examples': ['01-561'],
        'extract': _make_label_extractor(
            ['Customer #', 'Account #'], r'(\d{2}-\d{3,5})'),
    },

    # --- Tier 5 (10-14 failures) ---

    'Arrow Waste': {
        'has_account': True,
        'format': 'NN-NNNNNN',
        'examples': ['10-104710'],
        'extract': _make_label_extractor(
            ['Account #', 'Customer #'], r'(\d{2}-\d{5,7})'),
    },
    'City of Winfield': {
        'has_account': True,
        'format': 'NNNN/NNNN-N or NNNNNN',
        'examples': ['9001/2009-2', '105323'],
        'extract': _make_label_extractor(
            ['Account Number', 'Customer Number'],
            r'(\d{4}/\d{4}-\d|\d{5,7})'),
    },
    'H.E.R. TRUCKING INC': {
        'has_account': True,
        'format': 'NNNNN (5 digit)',
        'examples': ['11248'],
        'extract': _make_label_extractor(
            ['Account #', 'Customer #'], r'(\d{4,6})'),
    },
    'LJP Waste': {
        'has_account': True,
        'format': 'NN-NNNNNNN',
        'examples': ['10-7532277'],
        'extract': _make_label_extractor(
            ['Account #', 'Customer #'], r'(\d{2}-\d{5,8})'),
    },
    'Sound Disposal Inc': {
        'has_account': True,
        'format': 'NNNNNN (6 digit)',
        'examples': ['202806'],
        'extract': _make_label_extractor(
            ['Account #', 'Customer #'], r'(\d{5,7})'),
    },
    'City of Mount Vernon WA': {
        'has_account': True,
        'format': 'NN-NNNNNN',
        'examples': ['83-001720'],
        'extract': _make_label_extractor(
            ['Account #', 'Customer #'], r'(\d{2}-\d{5,7})'),
    },
    'Mountain High Disposal': {
        'has_account': True,
        'format': 'NN-NNNNNN',
        'examples': ['04-331419'],
        'extract': _make_label_extractor(
            ['Customer #', 'Account #'], r'(\d{2}-\d{5,7})'),
    },
    'Olathe Kansas': {
        'has_account': True,
        'format': 'CUST-NNNN',
        'examples': ['CUST-1641'],
        'extract': _make_label_extractor(
            ['Customer #', 'Account #'], r'(CUST-\d{3,5})'),
    },
    'All States Rentals': {
        'has_account': True,
        'format': 'NN-NNNNNNN',
        'examples': ['01-0100117'],
        'extract': _make_label_extractor(
            ['Customer #', 'Account #'], r'(\d{2}-\d{5,8})'),
    },
    'DISPOSAL & RECYCLING INC.': {
        'has_account': True,
        'format': 'NNNNNNN (7 digit)',
        'examples': ['2000065'],
        'extract': _make_label_extractor(
            ['Account #', 'Customer #'], r'(\d{6,8})'),
    },
    'IROW': {
        'has_account': True,
        'format': 'NNNNNN (6 digit)',
        'examples': ['002371'],
        'extract': _make_label_extractor(
            ['Customer #', 'Account #'], r'(\d{4,7})'),
    },
    'Murray Sanitation': {
        'has_account': True,
        'format': 'NN-NNN',
        'examples': ['03-496'],
        'extract': _make_label_extractor(
            ['Account #', 'Customer #'], r'(\d{2}-\d{3,5})'),
    },
    'PRAIRIE WASTE SOLUTIONS': {
        'has_account': True,
        'format': 'XXNNNN (alpha-prefix)',
        'examples': ['AC1402'],
        'extract': _make_label_extractor(
            ['Customer #', 'Account #'], r'([A-Z]{2}\d{3,6})'),
    },
    'Albuquerque Bernalillo County': {
        'has_account': True,
        'format': 'NNNNNNNNNN (10 digit)',
        'examples': ['1010779560'],
        'extract': _make_label_extractor(
            ['Account #', 'Account Number'], r'(\d{9,11})'),
    },
    'All States Services': {
        'has_account': True,
        'format': 'NN-NNNNNNN',
        'examples': ['09-0228745'],
        'extract': _make_label_extractor(
            ['Customer #', 'Account #'], r'(\d{2}-\d{5,8})'),
    },
    'CHOCTAW COUNTY WASTE SERVICES': {
        'has_account': True,
        'format': 'NNNNNN (6 digit)',
        'examples': ['305563'],
        'extract': _make_label_extractor(
            ['Account #', 'Customer #'], r'(\d{5,7})'),
    },
    'City of Garden City': {
        'has_account': True,
        'format': 'NNNNNN-NNN',
        'examples': ['025227-000'],
        'extract': _make_label_extractor(
            ['Account #', 'Customer #'], r'(\d{5,7}-\d{3})'),
    },
    'City of Tampa Utilities': {
        'has_account': True,
        'format': 'NNNNNNN (7 digit)',
        'examples': ['2192693'],
        'extract': _make_label_extractor(
            ['Account #', 'Account Number'], r'(\d{6,8})'),
    },
    'Kimble': {
        'has_account': True,
        'format': 'NNNNNN or NNNNNN-NNNN',
        'examples': ['174432', '552830-0001'],
        'extract': _make_label_extractor(
            ['Account #', 'Customer #'], r'(\d{5,7}(?:-\d{4})?)'),
    },
    'Noble County Disposal': {
        'has_account': True,
        'format': 'NNNNNNN (7 digit)',
        'examples': ['4364400'],
        'extract': _make_label_extractor(
            ['Account Number', 'Account #'], r'(\d{6,8})'),
    },
    'Redwood Waste': {
        'has_account': True,
        'format': 'NNNN-NNNNNNN',
        'examples': ['4039-6113030'],
        'extract': _make_label_extractor(
            ['Account #', 'Customer #'], r'(\d{4}-\d{5,8})'),
    },
    'Southern Oregon Sanitation': {
        'has_account': True,
        'format': 'NN-NNNNNNN',
        'examples': ['01-0075235'],
        'extract': _make_label_extractor(
            ['Account #', 'Customer #'], r'(\d{2}-\d{5,8})'),
    },
    'Waste Eliminator': {
        'has_account': True,
        'format': 'NN-NNNNN',
        'examples': ['01-12317'],
        'extract': _make_label_extractor(
            ['Customer Number', 'Customer #', 'Account #'], r'(\d{2}-\d{4,6})'),
    },
    'CITY OF KILLEEN': {
        'has_account': True,
        'format': 'NNNNNN-NNNNN',
        'examples': ['470077-69282'],
        'extract': _make_label_extractor(
            ['Customer ID-Location ID', 'Customer ID', 'Account #'],
            r'(\d{5,7}-\d{4,6})'),
    },
    'Eco-Tech': {
        'has_account': True,
        'format': 'NNNNNNN (7 digit)',
        'examples': ['7933303'],
        'extract': _make_label_extractor(
            ['Account Number', 'Account #'], r'(\d{6,8})'),
    },
    'PRIDE Disposal': {
        'has_account': True,
        'format': 'NNNNNNNN (8 digit)',
        'examples': ['01017092'],
        'extract': _make_label_extractor(
            ['Customer #', 'Account #'], r'(\d{7,9})'),
    },
    'R & W CONTAINER': {
        'has_account': True,
        'format': 'NNNN (4 digit)',
        'examples': ['5685'],
        'extract': _make_label_extractor(
            ['Account #', 'Customer #'], r'(\d{3,5})'),
    },
    'Virgin Valley Disposal': {
        'has_account': True,
        'format': 'NNNNN (5 digit)',
        'examples': ['11098'],
        'extract': _make_label_extractor(
            ['Account #', 'Customer #'], r'(\d{4,6})'),
    },
    'VLS Environmental': {
        'has_account': True,
        'format': 'NNNNNNNNN (9 digit)',
        'examples': ['935076775'],
        'extract': _make_label_extractor(
            ['Account #', 'Customer #'], r'(\d{8,10})'),
    },

    # --- Tier 6 (5-9 failures) ---

    'CAROLINA COMMERCIAL & INDUSTRIAL': {
        'has_account': True,
        'format': 'NNNNNNN (7 digit)',
        'examples': ['3018115'],
        'extract': _make_label_extractor(
            ['Customer #', 'Account #'], r'(\d{6,8})'),
    },
    'CLAY COUNTY REFUSE TAX OFFICE': {
        'has_account': True,
        'format': 'NNNNNN-N',
        'examples': ['225701-0'],
        'extract': _make_label_extractor(
            ['Account #', 'Customer #'], r'(\d{5,7}-\d)'),
    },
    'Cyclyx International LLC': {
        'has_account': True,
        'format': 'FT-NNNNNNN or 12-digit',
        'examples': ['FT-0000053'],
        'extract': _make_label_extractor(
            ['Account #', 'Customer #'], r'(FT-\d{5,8}|\d{10,13})'),
    },
    'GOT POOP': {
        'has_account': True,
        'format': 'XNNNN (alpha-prefix)',
        'examples': ['C6759'],
        'extract': _make_label_extractor(
            ['Customer #', 'ID#', 'Account #'], r'([A-Z]\d{3,6})'),
    },
    'Miller Waste Systems': {
        'has_account': True,
        'format': 'NNN-NNNNNN',
        'examples': ['115-008829'],
        'extract': _make_label_extractor(
            ['Customer #', 'Account #'], r'(\d{3}-\d{5,7})'),
    },
    'Secure Paper & Data Destruction': {
        'has_account': True,
        'format': 'NNNNNNNN (8 digit)',
        'examples': ['68255723'],
        'extract': _make_label_extractor(
            ['Account #', 'Customer #'], r'(\d{7,9})'),
    },
    'City of Fargo': {
        'has_account': True,
        'format': 'NNNNNNN (7 digit)',
        'examples': ['2205728'],
        'extract': _make_label_extractor(
            ['Account #', 'Customer #'], r'(\d{6,8})'),
    },
    'DTG Recycle': {
        'has_account': True,
        'format': 'NNNNNNNN (8 digit)',
        'examples': ['29147000'],
        'extract': _make_label_extractor(
            ['Account #', 'Customer #'], r'(\d{7,9})'),
    },
    'Pelican Waste': {
        'has_account': True,
        'format': 'NNNNNN (6 digit + site)',
        'examples': ['031803'],
        'extract': _make_label_extractor(
            ['Customer #', 'Site #', 'Account #'], r'(\d{5,7})'),
    },
    'RED OAK': {
        'has_account': True,
        'format': 'NNNNNNN (7 digit)',
        'examples': ['4643881'],
        'extract': _make_label_extractor(
            ['Account #', 'Customer #'], r'(\d{6,8})'),
    },
    'Sweetland': {
        'has_account': True,
        'format': 'NN-NNNNN',
        'examples': ['10-21420'],
        'extract': _make_label_extractor(
            ['Account #', 'Customer #'], r'(\d{2}-\d{4,6})'),
    },
    'Tate Services': {
        'has_account': True,
        'format': 'NNNNNN (6 digit + site)',
        'examples': ['014328'],
        'extract': _make_label_extractor(
            ['Customer #', 'Site #', 'Account #'], r'(\d{5,7})'),
    },
    "Thompson's Sanitary Service": {
        'has_account': True,
        'format': 'NNNNN (5 digit)',
        'examples': ['02314'],
        'extract': _make_label_extractor(
            ['Account #', 'Customer #'], r'(\d{4,6})'),
    },
    'Amwaste': {
        'has_account': True,
        'format': 'NNNN-NNNNN (4-5 digit)',
        'examples': ['98339', '4110'],
        'extract': _make_label_extractor(
            ['Customer #', 'Account #'], r'(\d{3,6})'),
    },
    'Balcones Recycling Dallas': {
        'has_account': True,
        'format': 'NNNNNNNNNN (10 digit)',
        'examples': ['1854040167'],
        'extract': _make_label_extractor(
            ['Account #', 'Customer #'], r'(\d{9,11})'),
    },
    'Blue Hen Dispose-All, Inc': {
        'has_account': True,
        'format': 'XXNNNNN (alpha-prefix)',
        'examples': ['BD21914'],
        'extract': _make_label_extractor(
            ['Customer #', 'Site #'], r'([A-Z]{2}\d{4,6})'),
    },
    'City of Henagar': {
        'has_account': True,
        'format': 'NN-NNNNN',
        'examples': ['10-49519'],
        'extract': _make_label_extractor(
            ['Account #', 'Customer #'], r'(\d{2}-\d{4,6})'),
    },
    'CR&R': {
        'has_account': True,
        'format': 'NN-NNNNNNN',
        'examples': ['77-0029708'],
        'extract': _make_label_extractor(
            ['Account #', 'Customer #'], r'(\d{2}-\d{5,8})'),
    },
    'SANTA CLARA VALLEY DISP': {
        'has_account': True,
        'format': 'N-NNNNNNN',
        'examples': ['3-0032020'],
        'extract': _make_label_extractor(
            ['Account #', 'Customer #'], r'(\d{1,2}-\d{5,8})'),
    },
    'Tooele County Solid Waste': {
        'has_account': True,
        'format': 'NNNNN-NNNNN',
        'examples': ['11064-21073'],
        'extract': _make_label_extractor(
            ['Account #', 'Customer #'], r'(\d{4,6}-\d{4,6})'),
    },
    'Ace Container - WP': {
        'has_account': True,
        'format': 'NNNN (4 digit)',
        'examples': ['2288'],
        'extract': _make_label_extractor(
            ['Site #', 'Account #'], r'(\d{3,5})'),
    },
    'Best Trash': {
        'has_account': True,
        'format': 'NNNNN (5 digit)',
        'examples': ['20593'],
        'extract': _make_label_extractor(
            ['Customer #', 'Account #'], r'(\d{4,6})'),
    },
    'Denali Disposal': {
        'has_account': True,
        'format': 'NNNNNNNNNN or NNNNNNNNN',
        'examples': ['8026513046', '599124169'],
        'extract': _make_label_extractor(
            ['Account #', 'Customer #'], r'(\d{8,11})'),
    },
    'Humboldt County Landfill': {
        'has_account': True,
        'format': 'NNNN (4 digit)',
        'examples': ['0077'],
        'extract': _make_label_extractor(
            ['Account #', 'Customer #'], r'(\d{3,5})'),
    },
    'LAUREL RIDGE LANDFILL LLC': {
        'has_account': True,
        'format': 'NNNN-NNN',
        'examples': ['6054-400'],
        'extract': _make_label_extractor(
            ['Account #', 'Customer #'], r'(\d{4}-\d{3})'),
    },
    'Legacy Disposal Services': {
        'has_account': True,
        'format': 'NNNNNN (6 digit + site)',
        'examples': ['215787'],
        'extract': _make_label_extractor(
            ['Account #', 'Site #'], r'(\d{5,7})'),
    },
    'Wall Recycling': {
        'has_account': True,
        'format': 'NN-NNNNN',
        'examples': ['01-61716'],
        'extract': _make_label_extractor(
            ['Customer #', 'Account #'], r'(\d{2}-\d{4,6})'),
    },
    'Waste Pro Oregon': {
        'has_account': True,
        'format': 'NNNNN (5 digit)',
        'examples': ['33622'],
        'extract': _make_label_extractor(
            ['Account #', 'Customer #'], r'(\d{4,6})'),
    },
    'ABC Waste': {
        'has_account': True,
        'format': 'NN-NNNNNNN',
        'examples': ['10-3313236'],
        'extract': _make_label_extractor(
            ['Account #', 'Customer #'], r'(\d{2}-\d{5,8})'),
    },
    'ALEX RUBBISH': {
        'has_account': True,
        'format': 'NNNNNNN (7 digit)',
        'examples': ['2325000'],
        'extract': _make_label_extractor(
            ['Account #', 'Customer #'], r'(\d{6,8})'),
    },
    'ALT REFUSE LTD': {
        'has_account': True,
        'format': 'NNNN (4 digit)',
        'examples': ['4570'],
        'extract': _make_label_extractor(
            ['Account #', 'Customer #'], r'(\d{3,5})'),
    },
    'American Metal and Paper': {
        'has_account': True,
        'format': 'NNNNN (5 digit)',
        'examples': ['50215'],
        'extract': _make_label_extractor(
            ['Account #', 'Customer #'], r'(\d{4,6})'),
    },
    'Arrowhead Waste': {
        'has_account': True,
        'format': 'NNNNNN (6 digit)',
        'examples': ['107236'],
        'extract': _make_label_extractor(
            ['Account #', 'Customer #'], r'(\d{5,7})'),
    },
    'Blue Diamond Disposal': {
        'has_account': True,
        'format': 'NNNNN (5 digit)',
        'examples': ['30239'],
        'extract': _make_label_extractor(
            ['Customer #', 'Site #'], r'(\d{4,6})'),
    },
    'Kurtz Sanitation': {
        'has_account': True,
        'format': 'NNN (3 digit)',
        'examples': ['810'],
        'extract': _make_label_extractor(
            ['Account #', 'Customer #'], r'(\d{3,5})'),
    },
    'Mid Florida Portable Toilet Services': {
        'has_account': True,
        'format': 'NNNNNN (6 digit)',
        'examples': ['001848'],
        'extract': _make_label_extractor(
            ['Customer #', 'Account #'], r'(\d{4,7})'),
    },
    "STAFFORD'S": {
        'has_account': True,
        'format': 'NNNNNN (6 digit + site)',
        'examples': ['281001'],
        'extract': _make_label_extractor(
            ['Account #', 'Site #'], r'(\d{5,7})'),
    },
    'ZTERS Inc': {
        'has_account': True,
        'format': 'NNNNNNN (7 digit)',
        'examples': ['2283230'],
        'extract': _make_label_extractor(
            ['Customer #', 'Account #'], r'(\d{6,8})'),
    },

    # --- Tier 7 (1-4 failures) ---

    '121 Disposal': {
        'has_account': True,
        'format': 'NNNNNNNN (8 digit)',
        'examples': ['12115951'],
        'extract': _make_label_extractor(
            ['Account #', 'Customer #'], r'(\d{7,9})'),
    },
    'ARROW DISPOSAL SERVICE, INC': {
        'has_account': True,
        'format': 'NN-NNNNN',
        'examples': ['01-1799'],
        'extract': _make_label_extractor(
            ['Customer #', 'Account #'], r'(\d{2}-\d{3,6})'),
    },
    'AWS- Affordable Waste Services': {
        'has_account': True,
        'format': 'NNNN (4 digit)',
        'examples': ['1053'],
        'extract': _make_label_extractor(
            ['Customer #', 'Account #'], r'(\d{3,5})'),
    },
    'C & C PORTABLES LLC - DUMPSTERS': {
        'has_account': True,
        'format': 'NNN (3 digit)',
        'examples': ['120'],
        'extract': _make_label_extractor(
            ['Account #', 'Customer #'], r'(\d{3,5})'),
    },
    'Emergency Sanitation Deployment LLC': {
        'has_account': True,
        'format': 'XXNNNNN (alpha-prefix)',
        'examples': ['CU01111'],
        'extract': _make_label_extractor(
            ['Customer #', 'Account #'], r'([A-Z]{2}\d{4,6})'),
    },
    'McAllen Public Utility': {
        'has_account': True,
        'format': 'NNNNNNN (7 digit)',
        'examples': ['0006376'],
        'extract': _make_label_extractor(
            ['Account #', 'Customer #'], r'(\d{5,8})'),
    },
    'Tonto Basin Sanitation': {
        'has_account': True,
        'format': 'NNNNNN (6 digit)',
        'examples': ['512375'],
        'extract': _make_label_extractor(
            ['Account #', 'Customer #'], r'(\d{5,7})'),
    },
    'TRASHCO': {
        'has_account': True,
        'format': 'NNNNN (5 digit)',
        'examples': ['11175'],
        'extract': _make_label_extractor(
            ['Account #', 'Customer #'], r'(\d{4,6})'),
    },
    'BERTOLOTTI CERES DISPOSAL': {
        'has_account': True,
        'format': 'NN-NNNNNNN',
        'examples': ['31-0027585'],
        'extract': _make_label_extractor(
            ['Account #', 'Customer #'], r'(\d{2}-\d{5,8})'),
    },
    'BRASK MALL SERVICES': {
        'has_account': True,
        'format': 'NN-NNNNNNN',
        'examples': ['81-0001050'],
        'extract': _make_label_extractor(
            ['Customer #', 'Account #'], r'(\d{2}-\d{5,8})'),
    },
    'KC Disposal': {
        'has_account': True,
        'format': 'NN-NNNNNN',
        'examples': ['02-630540'],
        'extract': _make_label_extractor(
            ['Customer #', 'Account #'], r'(\d{2}-\d{5,7})'),
    },
    'TOWN OF CENTRE, ALABAMA': {
        'has_account': True,
        'format': 'NNNNN (5 digit)',
        'examples': ['11052'],
        'extract': _make_label_extractor(
            ['Account #', 'Customer #'], r'(\d{4,6})'),
    },
    'Walters Recycling': {
        'has_account': True,
        'format': 'NNNNNN (6 digit)',
        'examples': ['254997'],
        'extract': _make_label_extractor(
            ['Account #', 'Customer #'], r'(\d{5,7})'),
    },
    'Winni Waste Solutions': {
        'has_account': True,
        'format': 'XNNN (alpha-prefix)',
        'examples': ['C668'],
        'extract': _make_label_extractor(
            ['Customer #', 'Account #'], r'([A-Z]\d{3,5})'),
    },
    'BRIDGEWATER CONSULTING LLC': {
        'has_account': True,
        'format': 'NNNNNNNNNNNNNN (14 digit)',
        'examples': ['15107612154726'],
        'extract': _make_label_extractor(
            ['Account #', 'Customer #'], r'(\d{12,15})'),
    },
    "Burgmeier's Hauling": {
        'has_account': True,
        'format': 'NNN (3 digit)',
        'examples': ['517'],
        'extract': _make_label_extractor(
            ['Customer #', 'Account #'], r'(\d{3,5})'),
    },
    'Centennial Park Disposal': {
        'has_account': True,
        'format': 'NNNNN (5 digit)',
        'examples': ['10662'],
        'extract': _make_label_extractor(
            ['Account #', 'Customer #'], r'(\d{4,6})'),
    },
    'Disposal Services LLC': {
        'has_account': True,
        'format': 'NNNN (4 digit)',
        'examples': ['3896'],
        'extract': _make_label_extractor(
            ['Account #', 'Customer #'], r'(\d{3,5})'),
    },
    'Eco Waste': {
        'has_account': True,
        'format': 'NNNNNN (6 digit)',
        'examples': ['191909'],
        'extract': _make_label_extractor(
            ['Account #', 'Customer #'], r'(\d{5,7})'),
    },
    'GAUTHIER TRUCKING CO': {
        'has_account': True,
        'format': 'NNNNN (5 digit)',
        'examples': ['32642'],
        'extract': _make_label_extractor(
            ['Account #', 'Customer #'], r'(\d{4,6})'),
    },
    'Heiberg Garbage': {
        'has_account': True,
        'format': 'NNNNNN (6 digit)',
        'examples': ['137845'],
        'extract': _make_label_extractor(
            ['Account #', 'Customer #'], r'(\d{5,7})'),
    },
    'Key Disposal & Recycling': {
        'has_account': True,
        'format': 'NNNNNNNNNN (10 digit)',
        'examples': ['3818686627'],
        'extract': _make_label_extractor(
            ['Account #', 'Customer #'], r'(\d{9,11})'),
    },
    'Lakeshore Recycling': {
        'has_account': True,
        'format': 'NNNNNNNNN (9 digit)',
        'examples': ['792895150'],
        'extract': _make_label_extractor(
            ['Account #', 'Customer #'], r'(\d{8,10})'),
    },
    'LRS Waste': {
        'has_account': True,
        'format': 'NNNNNN (6 digit)',
        'examples': ['692559'],
        'extract': _make_label_extractor(
            ['Customer #', 'Account #'], r'(\d{5,7})'),
    },
    'Metalpro': {
        'has_account': True,
        'format': 'XXNNNN (alpha-prefix)',
        'examples': ['MD0658'],
        'extract': _make_label_extractor(
            ['ID#', 'Account #', 'Customer #'], r'([A-Z]{2}\d{3,5})'),
    },
    'Walters Sanitary Service': {
        'has_account': True,
        'format': 'NNNNNN (6 digit)',
        'examples': ['508897'],
        'extract': _make_label_extractor(
            ['Account #', 'Customer #'], r'(\d{5,7})'),
    },
    'West Central Sanitation': {
        'has_account': True,
        'format': 'NNNNNNNN (8 digit)',
        'examples': ['19834000'],
        'extract': _make_label_extractor(
            ['Account #', 'Customer #'], r'(\d{7,9})'),
    },
    'Ada County Trash Billing': {
        'has_account': True,
        'format': 'NNNNNN (6 digit)',
        'examples': ['512055'],
        'extract': _make_label_extractor(
            ['Account #', 'Customer #'], r'(\d{5,7})'),
    },
    'CENTRAL KENTUCKY HAULING': {
        'has_account': True,
        'format': 'NN-NNNNN',
        'examples': ['01-25448'],
        'extract': _make_label_extractor(
            ['Customer #', 'Account #'], r'(\d{2}-\d{4,6})'),
    },
    'Clackamas Garbage': {
        'has_account': True,
        'format': 'NNNNN (5 digit)',
        'examples': ['07061'],
        'extract': _make_label_extractor(
            ['Account #', 'Customer #'], r'(\d{4,6})'),
    },
    "Dan's Sanitation": {
        'has_account': True,
        'format': 'NNNNNN (6 digit)',
        'examples': ['116072'],
        'extract': _make_label_extractor(
            ['Account #', 'Customer #'], r'(\d{5,7})'),
    },
    'Ely Disposal Service': {
        'has_account': True,
        'format': 'NNNNNN (6 digit)',
        'examples': ['118494'],
        'extract': _make_label_extractor(
            ['Account #', 'Customer #'], r'(\d{5,7})'),
    },
    'G & H Garbage': {
        'has_account': True,
        'format': 'NNXNNNNN (alphanumeric)',
        'examples': ['61X02925'],
        'extract': _make_label_extractor(
            ['Account #', 'Customer #'], r'(\d{2}[A-Z]\d{4,6})'),
    },
    "George's Salvage Co": {
        'has_account': True,
        'format': 'NNNNNN (6 digit)',
        'examples': ['108031'],
        'extract': _make_label_extractor(
            ['Customer #', 'Account #'], r'(\d{5,7})'),
    },
    'Gilton Solid Waste': {
        'has_account': True,
        'format': 'NNNNNN (6 digit)',
        'examples': ['857542'],
        'extract': _make_label_extractor(
            ['Customer #', 'Account #'], r'(\d{5,7})'),
    },
    'Innovate Crushing and Aggregate': {
        'has_account': True,
        'format': 'NNNN (4 digit)',
        'examples': ['1186'],
        'extract': _make_label_extractor(
            ['Account #', 'Customer #'], r'(\d{3,5})'),
    },
    'K Secure Shredding, LLC': {
        'has_account': True,
        'format': 'NNNNNN (6 digit)',
        'examples': ['629780'],
        'extract': _make_label_extractor(
            ['Account #', 'Customer #'], r'(\d{5,7})'),
    },
    'Newlife Trust': {
        'has_account': True,
        'format': 'NNNNNNNNNN (10 digit)',
        'examples': ['6066583755'],
        'extract': _make_label_extractor(
            ['Account #', 'Customer #'], r'(\d{9,11})'),
    },
    'Tiger Sanitation': {
        'has_account': True,
        'format': 'NNNNNN (6 digit + site)',
        'examples': ['325186'],
        'extract': _make_label_extractor(
            ['Account #', 'Site #'], r'(\d{5,7})'),
    },

    # --- UNCERTAIN → HAS_ACCOUNT reclassifications ---

    'Nauset Disposal': {
        'has_account': True,
        'format': 'NNNN-NNNNNNNN',
        'examples': ['6275-90427000'],
        'extract': _make_label_extractor(
            ['Account No', 'Account #'], r'(\d{4}-\d{6,9})'),
    },
    'Suburban Disposal': {
        'has_account': True,
        'format': 'NNNNNN-NNN',
        'examples': ['099323-000'],
        'extract': _make_label_extractor(
            ['Account No', 'Account #'], r'(\d{5,7}-\d{3})'),
    },
    'Pellitteri': {
        'has_account': True,
        'format': 'NNNNNNNN (8 digit)',
        'examples': ['18859300'],
        'extract': _make_label_extractor(
            ['Account Number', 'Account #'], r'(\d{7,9})', max_lines=10),
    },
    'All American Waste': {
        'has_account': True,
        'format': 'NNNNNN (6 digit)',
        'examples': ['207498'],
        'extract': _make_label_extractor(
            ['Account Number', 'Account #'], r'(\d{5,8})', max_lines=12),
    },
    'Kootenai County Solid Waste': {
        'has_account': True,
        'format': 'NN-NNNNN.NN',
        'examples': ['10-86893.00', '10-80606.00'],
        'extract': _make_label_extractor(
            ['Solid Waste Acct #', 'Acct #', 'Account #'],
            r'(\d{2}-\d{4,6}(?:\.\d{2})?)'),
    },
    'ZOOM': {
        'has_account': True,
        'format': 'NNNNNNNN (8 digit)',
        'examples': ['51166039'],
        'extract': _make_label_extractor(
            ['Account Number', 'Account #'], r'(\d{7,9})'),
    },
    'Waste Masters': {
        'has_account': True,
        'format': 'NNNNNN-NNNN',
        'examples': ['008252-0000'],
        'extract': _make_label_extractor(
            ['ACCOUNT', 'Account #'], r'(\d{5,7}-\d{4})'),
    },
    'Advance Disposal': {
        'has_account': True,
        'format': 'NNNNNNNNNN (10 digit)',
        'examples': ['0002516362'],
        'extract': _make_label_extractor(
            ['CUSTOMER NO', 'Customer #', 'Account #'], r'(\d{8,11})', max_lines=10),
    },
    'BELMONT WASTE DISPOSAL': {
        'has_account': True,
        'format': 'NN-NNNN',
        'examples': ['01-6460'],
        'extract': _make_label_extractor(
            ['Customer Number', 'Customer #'], r'(\d{2}-\d{4,5})'),
    },
    'KANSAS NORTH LLC': {
        'has_account': True,
        'format': 'NNNNNNNNN (alphanumeric)',
        'examples': ['15649080T'],
        'extract': _make_label_extractor(
            ['ACCT', 'Account #'], r'(\d{6,10}[A-Z]?)'),
    },
    'Ohio Valley Waste': {
        'has_account': True,
        'format': 'NN-NNNN',
        'examples': ['90-5773'],
        'extract': _make_label_extractor(
            ['Account number', 'Account #'], r'(\d{2}\s*-\s*\d{4,5})'),
    },
    'Redgate Disposal': {
        'has_account': True,
        'format': 'XNNNN (alpha-prefix)',
        'examples': ['C8454'],
        'extract': _make_label_extractor(
            ['Account #', 'Customer #'], r'([A-Z]\d{3,6})'),
    },
    'Impact Environmental': {
        'has_account': True,
        'format': 'XX_NNNNN (alpha_prefix)',
        'examples': ['FG_11645'],
        'extract': _make_label_extractor(
            ['Customer #', 'Account #'], r'([A-Z]{2}[_-]\d{4,6})'),
    },
    'Waste Services Inc': {
        'has_account': True,
        'format': 'NNNNNNN (7 digit)',
        'examples': ['2571300'],
        'extract': _make_label_extractor(
            ['CUST NO', 'Customer No', 'Customer #'], r'(\d{6,8})'),
    },
    'Compactor Rentals of America': {
        'has_account': True,
        'format': 'NNNN (4 digit)',
        'examples': ['2158'],
        'extract': _make_label_extractor(
            ['Customer #', 'Account #'], r'(\d{3,5})'),
    },
    'Marpan Supply': {
        'has_account': True,
        'format': 'NNNNNN (6 digit)',
        'examples': ['007887'],
        'extract': _make_label_extractor(
            ['Account ID', 'Account #'], r'(\d{4,7})'),
    },
    'GHW Waste': {
        'has_account': True,
        'format': 'NNNN (4 digit)',
        'examples': ['2259'],
        'extract': _make_label_extractor(
            ['CUSTOMER NO', 'Customer #'], r'(\d{3,5})'),
    },
    'Hopkinsville Solid Waste': {
        'has_account': True,
        'format': 'NNN (3 digit)',
        'examples': ['110'],
        'extract': _make_label_extractor(
            ['ACCOUNT', 'Account #'], r'(\d{3,5})'),
    },
    'Iron Mountain': {
        'has_account': True,
        'format': 'XXXNN (alphanumeric, before /NAME)',
        'examples': ['SB358'],
        'extract': lambda text: (
            # Iron Mountain: "Customer ID/Name:|SB358/LAM RESEARCH"
            (lambda m: m.group(1) if m else None)(
                re.search(r'Customer\s*ID(?:/Name)?[:\s|]*([A-Z]{2,4}\d{2,5})',
                          text.replace('\\n', '\n'), re.I))
        ),
    },

    # ----------------------------------------------------------
    # ADDITIONAL SPECIFIC VENDORS (from review analysis)
    # ----------------------------------------------------------

    # Recycling Services of Florida and F & L Construction — entries moved to
    # Tier 1-2 section with correct labels (see ~line 848/869)
    'Boise City of Trees': {
        'has_account': True,
        'format': 'NNNNNNNNNNNNNNN (15 digit)',
        'examples': ['058961700347545'],
        'extract': _make_label_extractor(
            ['Account Number', 'Account #'], r'(\d{12,16})'),
    },
    'Cogent Waste Solutions': {
        'has_account': True,
        'format': 'NNNNNNN (7 digit)',
        'examples': ['2860921'],
        'extract': _make_label_extractor(
            ['Customer #', 'Account Number', 'Act Nbr'], r'(\d{6,8})'),
    },
    # ----- New vendors from corpus analysis (not previously in v93d) -----
    'Solid Waste Authority': {
        'has_account': True,
        'format': '3-6 digit customer number',
        'examples': ['1526'],
        'extract': _make_label_extractor(
            ['Customer Number', 'Customer No', 'Account #'], r'(\d{3,6})', max_lines=6),
    },
    'Waste Pro': {
        'has_account': True,
        'format': 'Various: Z-10, 02-0201795 0, 02-100-52525-00-045904',
        'examples': ['Z-10', '02-0201795 0', '02-100-52525-00-045904'],
        'extract': _extract_waste_pro_v2,
    },
    'City Waste': {
        'has_account': True,
        'format': 'Various: NNNNNN-NNNNNN (City of Tyler), NNNNN (Boro Wide)',
        'examples': ['230131-113498', '36640'],
        'extract': _make_label_extractor(
            ['ACCOUNT', 'Account', 'Customer No', 'CUSTOMER NO'],
            r'(\d{5,6}(?:-\d{5,6})?)', max_lines=6),
    },
    'City of Jackson': {
        'has_account': True,
        'format': 'Various: G528 (alpha-prefix), NNNNNN-NNNNN',
        'examples': ['G528', '203809-21438'],
        'extract': _make_label_extractor(
            ['Customer ID', 'Account Number', 'Account #'],
            r'([A-Z]\d{2,4}|\d{5,6}-\d{4,6})', max_lines=6),
    },
    'Athens Services': {
        'has_account': True,
        'format': 'XX-NNNNNNN (2 alpha + 7 digit)',
        'examples': ['TH-0054512', 'CV-0012008'],
        'extract': _make_label_extractor(
            ['ACCOUNT NUMBER', 'Account Number', 'ACCOUNT #'],
            r'([A-Z]{2}-?\d{7})', max_lines=6),
    },
    'Meridian Waste': {
        'has_account': True,
        'format': 'NN-NNNN N (BRT format)',
        'examples': ['07-5910 0', '70-7608 6'],
        'extract': _make_label_extractor(
            ['Account No', 'Account Number', 'Account #'],
            r'(\d{2}-\d{4,7}\s*\d?)', max_lines=6),
    },
    'Bruin Waste Management': {
        'has_account': True,
        'format': 'NNNNN (5 digit)',
        'examples': ['25172'],
        'extract': _make_label_extractor(
            ['ACCOUNT #', 'Account #'], r'(\d{4,6})', max_lines=8),
    },
    'Pratt Recycling': {
        'has_account': True,
        'format': 'NNNN (4 digit customer no)',
        'examples': ['7597', '283172'],
        'extract': _make_label_extractor(
            ['CUSTOMER NO', 'Customer No', 'Customer'], r'(\d{4,6})', max_lines=6),
    },
    'Apex Waste': {
        'has_account': True,
        'format': 'DM + 4 digit or 6-8 digit',
        'examples': ['DM8468'],
        'extract': _make_label_extractor(
            ['Account #', 'ACCOUNT #'], r'([A-Z]{2}\d{4,6}|\d{6,8})', max_lines=8),
    },
    'The Good Guys': {
        'has_account': True,
        'format': 'XXXXX-XXXXX (alphanumeric with dash)',
        'examples': ['77RYR-PX8MM', 'W43HX-AYG6S'],
        'extract': _make_label_extractor(
            ['Account ID', 'Account #'], r'([A-Z0-9]{5}-[A-Z0-9]{5})', max_lines=6),
    },
    "Doll's Disposal LLC": {
        'has_account': True,
        'format': 'NNNNNN (payment portal)',
        'examples': ['000941'],
        'extract': _extract_payment_portal_account,
    },

    # ----------------------------------------------------------
    # WM NATIONAL ACCOUNT format (v93d fallback for misdetected subsidiaries)
    # ----------------------------------------------------------
    'Waste Management': {
        'has_account': True,
        'format': 'WGY code, NN-NNNNN-NNNNN, ACCT #, Account Number',
        'examples': ['WGY20070UP', '25-34374-43006', '72423', '00615'],
        'extract': _extract_wm_national_account,
    },
    'USA Waste': {
        'has_account': True,
        'format': 'WM Customer ID or Account Number (various)',
        'examples': ['25-34374-43006', '267490', 'W13628'],
        'extract': _extract_wm_national_account,
    },
}

# ============================================================
# ROUND 3 — Step 3 review grind (remaining 1,472 failures)
# ============================================================

# --- Custom extractors for complex formats ---

def _extract_iron_mountain_v2(text: str) -> Optional[str]:
    """Iron Mountain: Customer ID/Name: 2B2ZN/WASTEOLOGY GROUP/"""
    normalized = text.replace('\\n', '\n')
    # Customer ID/Name: VALUE/
    m = re.search(r'Customer\s*ID/Name:\s*\n?\s*([A-Z0-9]{3,12})/', normalized, re.I)
    if m:
        return m.group(1)
    return _extract_by_label(text, ['Customer ID'], r'([A-Z0-9]{3,12})', max_lines=4)


def _extract_best_way_v2(text: str) -> Optional[str]:
    """Best Way Disposal: Account# D. 161766100 (letter prefix + digits)"""
    normalized = text.replace('\\n', '\n')
    # Account# D. 161766100 or Account# 161766100
    m = re.search(r'Account\s*#\s*:?\s*\n?\s*(?:[A-Z]\.\s*)?(\d{6,10})', normalized, re.I)
    if m:
        return m.group(1)
    return _extract_by_label(text, ['Account #'], r'([A-Z]\.?\s*\d{6,10})', max_lines=4)


def _extract_envirotech(text: str) -> Optional[str]:
    """ENVIROTECH WASTE: DISTRICT NO. 3033 + ACCOUNT NO. 3033-229727"""
    normalized = text.replace('\\n', '\n')
    m = re.search(r'ACCOUNT\s*NO\.?\s*:?\s*\n?\s*(\d{3,4}-\d{5,7})', normalized, re.I)
    if m:
        return m.group(1)
    return _extract_by_label(text, ['Account #', 'Account No'], r'(\d{3,8})', max_lines=4)


def _extract_city_of_oakland_park(text: str) -> Optional[str]:
    """City of Oakland Park: Account Number - Customer Number in billing header"""
    normalized = text.replace('\\n', '\n')
    # Account Number followed by number
    m = re.search(r'Account\s*Number\s*(?:-\s*Customer\s*Number)?\s*\n?\s*(?:Current[^\n]*\n)?\s*(\d{5,10})', normalized, re.I)
    if m:
        return m.group(1)
    return _extract_by_label(text, ['Account Number'], r'(\d{5,10})', max_lines=6)


def _extract_bruin_waste_v2(text: str) -> Optional[str]:
    """Bruin Waste: CUSTOMER NO + QUICK PAY CODE (use CUSTOMER NO if present, else QUICK PAY CODE)"""
    normalized = text.replace('\\n', '\n')
    # CUSTOMER NO on label line, value on next line or inline
    m = re.search(r'CUSTOMER\s*NO\.?\s*:?\s*\n?\s*(\d{4,8})', normalized, re.I)
    if m:
        return m.group(1)
    # QUICK PAY CODE
    m = re.search(r'QUICK\s*PAY\s*CODE\s*:?\s*\n?\s*(\d{4,8})', normalized, re.I)
    if m:
        return m.group(1)
    return _extract_by_label(text, ['Customer #'], r'(\d{4,8})', max_lines=6)


def _extract_texas_disposal_v2(text: str) -> Optional[str]:
    """Texas Disposal / All Waste / Cards KS / Aspen Waste.
    Format: Account #: on one line, number with spaces several lines below.
    Example: Account #: \\n Balance Due: \\n ... \\n 1 -269891 5
    Also: Account Number: 1 -269891 5 (inline with spaces)
    """
    normalized = text.replace('\\n', '\n')
    # Try inline first: Account Number: 1 -269891 5
    m = re.search(r'Account\s*(?:Number|No\.?|#)\s*:?\s*(\d[\d\s\-]{4,15}\d)', normalized, re.I)
    if m:
        return re.sub(r'\s+', '', m.group(1))
    # Multi-line: find Account label, then scan next 8 lines for digit-dash-space pattern
    lines = normalized.split('\n')
    for i, line in enumerate(lines):
        if re.search(r'Account\s*(?:#|No\.?|Number)\s*:?', line, re.I):
            for j in range(i + 1, min(i + 8, len(lines))):
                val = lines[j].strip()
                # Match digit patterns with spaces: "1 -269891 5", "21-37537 5", "1-50232 5"
                m2 = re.match(r'^(\d[\d\s\-]{4,15}\d)\s*$', val)
                if m2:
                    return re.sub(r'\s+', '', m2.group(1))
    return None


def _extract_star_waste_v2(text: str) -> Optional[str]:
    """Star Waste: ACCOUNT NUMBER \\n AC 8 8 7 7T (OCR garbles spacing)"""
    normalized = text.replace('\\n', '\n')
    lines = normalized.split('\n')
    for i, line in enumerate(lines):
        if re.search(r'ACCOUNT\s*NUMBER', line, re.I):
            # Check next 3 lines for alphanumeric value (possibly with spaces)
            for j in range(i, min(i + 4, len(lines))):
                # Inline on same line
                m = re.search(r'ACCOUNT\s*NUMBER\s*:?\s+([A-Z0-9][\sA-Z0-9]{3,15})', lines[j], re.I)
                if m:
                    return re.sub(r'\s+', '', m.group(1))
                # On subsequent line — any alphanumeric sequence (collapse spaces)
                if j > i:
                    val = lines[j].strip()
                    if re.match(r'^[A-Z0-9][\sA-Z0-9]{3,15}$', val) and not val.startswith('LOCATION'):
                        return re.sub(r'\s+', '', val)
    return _extract_by_label(text, ['Account #'], r'([A-Z0-9]{4,10})', max_lines=6)


def _extract_direct_waste_v2(text: str) -> Optional[str]:
    """Direct Waste Services: Account ID#: 4107"""
    normalized = text.replace('\\n', '\n')
    m = re.search(r'Account\s*ID\s*#?\s*:?\s*\n?\s*(\d{3,8})', normalized, re.I)
    if m:
        return m.group(1)
    return _extract_by_label(text, ['Account #', 'Customer #'], r'(\d{3,8})', max_lines=6)


def _extract_tooele_county(text: str) -> Optional[str]:
    """Tooele County: CUSTOMER NO. + multi-line → PARCEL ID or ACCOUNT"""
    normalized = text.replace('\\n', '\n')
    # CUSTOMER NO. → next non-empty line
    m = re.search(r'CUSTOMER\s*NO\.?\s*:?\s*\n?\s*(\d{4,8})', normalized, re.I)
    if m:
        return m.group(1)
    # ACCOUNT field
    m = re.search(r'\bACCOUNT\s+(\d{5}-\d{5})', normalized, re.I)
    if m:
        return m.group(1)
    return _extract_by_label(text, ['Customer #'], r'(\d{4,8})', max_lines=6)


def _extract_intermountain_disposal(text: str) -> Optional[str]:
    """Intermountain Disposal: Customer ID + Account code LDS"""
    normalized = text.replace('\\n', '\n')
    m = re.search(r'Customer\s*ID\s*:?\s*\n?\s*([A-Z0-9]{2,10})', normalized, re.I)
    if m:
        val = m.group(1)
        if len(val) >= 2:
            return val
    m = re.search(r'Account\s*code\s*:?\s*\n?\s*([A-Z0-9]{2,10})', normalized, re.I)
    if m:
        return m.group(1)
    return None


def _extract_cavossa_disposal(text: str) -> Optional[str]:
    """Cavossa Disposal: Cust ID: 133508"""
    normalized = text.replace('\\n', '\n')
    m = re.search(r'Cust\s*ID\s*:?\s*\n?\s*(\d{4,8})', normalized, re.I)
    if m:
        return m.group(1)
    return _extract_by_label(text, ['Customer #', 'Account #'], r'(\d{4,8})', max_lines=6)


def _extract_coastal_waste_v2(text: str) -> Optional[str]:
    """Coastal Waste: Account Number: 7029187197 (in ACH section or header)"""
    normalized = text.replace('\\n', '\n')
    # Skip routing numbers, look for account-context numbers
    m = re.search(r'(?:Customer|Account)\s*(?:Number|#|No)\s*:?\s*\n?\s*(\d{6,12})', normalized, re.I)
    if m:
        return m.group(1)
    return _extract_by_label(text, ['Account #'], r'(\d{6,12})', max_lines=6)


def _extract_glendale_az_utilities(text: str) -> Optional[str]:
    """Glendale AZ Utilities: VALUE appears BEFORE label.
    Format: 00321190-00 \\n ACCOUNT NUMBER: \\n 05/01/2025"""
    normalized = text.replace('\\n', '\n')
    # Try inline first
    m = re.search(r'ACCOUNT\s*NUMBER\s*:?\s*(\d{8,10}-\d{2})', normalized, re.I)
    if m:
        return m.group(1)
    # Backward search: value appears on line BEFORE the label
    lines = normalized.split('\n')
    for i, line in enumerate(lines):
        if re.search(r'ACCOUNT\s*NUMBER', line, re.I):
            # Check previous lines for the value
            for j in range(i - 1, max(i - 4, -1), -1):
                val = lines[j].strip()
                m2 = re.match(r'^(\d{6,10}-\d{2})$', val)
                if m2:
                    return m2.group(1)
            # Also check next lines
            for j in range(i + 1, min(i + 4, len(lines))):
                val = lines[j].strip()
                m2 = re.match(r'^(\d{6,10}-\d{2})', val)
                if m2:
                    return m2.group(1)
    return _extract_by_label(text, ['Account #'], r'(\d{5,12}(?:-\d{2})?)', max_lines=6, backward=True)


def _extract_wb_waste(text: str) -> Optional[str]:
    """WB Waste Solutions: number near header (no label), 9-digit format"""
    normalized = text.replace('\\n', '\n')
    lines = normalized.split('\n')
    # Look for standalone 9-digit number in first 10 lines
    for line in lines[:10]:
        m = re.match(r'^\s*(\d{9})\s*$', line.strip())
        if m:
            return m.group(1)
    return _extract_by_label(text, ['Account #', 'Customer #'], r'(\d{6,10})', max_lines=8)


def _extract_northern_waste_v2(text: str) -> Optional[str]:
    """Northern Waste (WM invoice detail format):
    Headers: LOCATION ID/COMPANY CODE/GL ACCOUNT | SERVICE NAME/ | SERVICE ADDRESS/ | VENDOR ACCOUNT NUMBER
    Data rows follow in columnar layout with vendor account number as a column."""
    normalized = text.replace('\\n', '\n')
    # Try VENDOR ACCOUNT NUMBER header → scan data rows
    lines = normalized.split('\n')
    for i, line in enumerate(lines):
        if 'VENDOR ACCOUNT NUMBER' in line.upper():
            for j in range(i + 1, min(i + 30, len(lines))):
                val = lines[j].strip()
                m2 = re.match(r'^(\d{2,3}-\d{5,8})\b', val)
                if m2:
                    return m2.group(1)
                m2 = re.match(r'^(\d{5,10})\b', val)
                if m2:
                    return m2.group(1)
    # Try ACCOUNT NAME → sometimes account info is nearby
    m = re.search(r'(?:ACCOUNT|Account)\s*(?:NAME|Number|#|No)\s*:?\s*\n?\s*([A-Z0-9][\w\-]{3,15})', normalized, re.I)
    if m and m.group(1).upper() not in ('WASTEOLOGY', 'GROUP'):
        return m.group(1)
    return None


def _extract_hopkinsville_sw(text: str) -> Optional[str]:
    """Hopkinsville Solid Waste Enterprise: ACCOUNT NUMBER multi-line + ticket format"""
    normalized = text.replace('\\n', '\n')
    m = re.search(r'(?:ACCOUNT|Account)\s*(?:NUMBER|#|No)\s*:?\s*\n?\s*(\d{3,8})', normalized, re.I)
    if m:
        return m.group(1)
    # CUSTOMER NO format
    m = re.search(r'CUSTOMER\s*NO\.?\s*:?\s*\n?\s*(\d{3,8})', normalized, re.I)
    if m:
        return m.group(1)
    return None


def _extract_stericycle_v2(text: str) -> Optional[str]:
    """Stericycle: Customer No (Payer) 1000998553"""
    normalized = text.replace('\\n', '\n')
    m = re.search(r'Customer\s*No\.?\s*(?:\(Payer\))?\s*:?\s*\n?\s*(\d{8,12})', normalized, re.I)
    if m:
        return m.group(1)
    return _extract_by_label(text, ['Customer #', 'Account #'], r'(\d{6,12})', max_lines=6)


def _extract_valley_vista_v2(text: str) -> Optional[str]:
    """Valley Vista: Account # multi-line"""
    normalized = text.replace('\\n', '\n')
    m = re.search(r'Account\s*#\s*:?\s*\n?\s*([A-Z0-9]{3,10})', normalized, re.I)
    if m:
        return m.group(1)
    return _extract_by_label(text, ['Account #', 'Customer #'], r'([A-Z0-9]{3,10})', max_lines=6)


# --- Round 3 vendor additions (override entries) ---

_ROUND3_VENDOR_ADDITIONS = {
    # NEW vendors (no pattern in engine)
    'DISPOSAL & RECYCLING INC. Aloha, OR 97006': {
        'has_account': True,
        'format': 'Account No. NNNNNNN (Evergreen)',
        'examples': ['2000065'],
        'extract': _make_label_extractor(['Account No', 'Account #'], r'(\d{5,8})', max_lines=6),
    },
    'ENVIROTECH WASTE SERVICES': {
        'has_account': True,
        'format': 'NNNN-NNNNNN (district-account)',
        'examples': ['3033-229727'],
        'extract': _extract_envirotech,
    },
    'Royal Carting Service': {
        'has_account': True,
        'format': 'Account Number: NNNNNN',
        'examples': ['900890'],
        'extract': _make_label_extractor(['Account Number', 'Account #'], r'(\d{5,8})', max_lines=6),
    },
    'WASTEQUIP': {
        'has_account': True,
        'format': 'Account Number in column-header layout',
        'examples': ['22067'],
        'extract': _make_label_extractor(['Account Number', 'Account #'], r'(\d{4,8})', max_lines=12),
    },
    'Alamo Disposal': {
        'has_account': True,
        'format': 'Customer Number: NNNN',
        'examples': ['1200', '09841'],
        'extract': _make_label_extractor(['Customer Number', 'Customer #'], r'(\d{3,6})', max_lines=6),
    },
    'ADA County': {
        'has_account': True,
        'format': 'ACCOUNT# NNNNNN',
        'examples': ['512077'],
        'extract': _make_label_extractor(['ACCOUNT#', 'Account #'], r'(\d{5,8})', max_lines=6),
    },
    'City of Riverton': {
        'has_account': True,
        'format': 'Account Number: NNNNNB-NN (multi-line)',
        'examples': ['06149B-00'],
        'extract': _make_label_extractor(['Account Number'], r'(\d{4,6}[A-Z]?-\d{2})', max_lines=8),
    },
    'Emergency Sanitation Deployment LLC DBA': {
        'has_account': True,
        'format': 'Customer ID: CUNNNN',
        'examples': ['CU01111'],
        'extract': _make_label_extractor(['Customer ID'], r'([A-Z]{2}\d{4,6})', max_lines=4),
    },
    'Floaters Portable Sanitation': {
        'has_account': True,
        'format': 'Cust # NNNNNNN',
        'examples': ['4322900'],
        'extract': _make_label_extractor(['Cust #', 'Customer #'], r'(\d{5,8})', max_lines=4),
    },
    'Hopkinsville Solid Waste Enterprise': {
        'has_account': True,
        'format': 'ACCOUNT NUMBER multi-line',
        'examples': ['110'],
        'extract': _extract_hopkinsville_sw,
    },
    'A-1 INDUSTRIAL MAINTENANCE, INC': {
        'has_account': True,
        'format': 'Customer ID + PO reference',
        'examples': ['16302'],
        'extract': _make_label_extractor(['Customer ID', 'Customer #'], r'(\d{4,8})', max_lines=4),
    },

    # EXISTING vendors (override — edge case formats not handled by base)
    'Idaho Falls Utilities': {
        'has_account': True,
        'format': 'Customer # CNNNN (letter prefix)',
        'examples': ['C00118'],
        'extract': _make_label_extractor(['Customer #', 'Customer No'], r'([A-Z]\d{4,6})', max_lines=4),
    },
    'Iron Mountain': {
        'has_account': True,
        'format': 'Customer ID/Name: VALUE/',
        'examples': ['2B2ZN'],
        'extract': _extract_iron_mountain_v2,
    },
    'Best Way Disposal': {
        'has_account': True,
        'format': 'Account# D. NNNNNNNNN',
        'examples': ['161766100'],
        'extract': _extract_best_way_v2,
    },
    'Boro Wide': {
        'has_account': True,
        'format': 'CUSTOMER NO. NNNN',
        'examples': ['9952'],
        'extract': _make_label_extractor(['CUSTOMER NO', 'Customer #'], r'(\d{3,6})', max_lines=6),
    },
    'City of Oakland Park': {
        'has_account': True,
        'format': 'Account Number - Customer Number NNNNNN',
        'examples': ['10983'],
        'extract': _extract_city_of_oakland_park,
    },
    'Bruin Waste Management': {
        'has_account': True,
        'format': 'CUSTOMER NO or QUICK PAY CODE',
        'examples': ['76039'],
        'extract': _extract_bruin_waste_v2,
    },
    'City of Jackson': {
        'has_account': True,
        'format': 'CUSTOMER NO. NNNNN',
        'examples': ['48749'],
        'extract': _make_label_extractor(['CUSTOMER NO', 'Customer #', 'Account #'], r'(\d{4,8})', max_lines=6),
    },
    'Liberty Waste': {
        'has_account': True,
        'format': 'Account Number NNNNNN',
        'examples': ['012407'],
        'extract': _make_label_extractor(['Account Number', 'Account #'], r'(\d{5,8})', max_lines=4),
    },
    'NVA Services': {
        'has_account': True,
        'format': 'Account Number NNNNNN',
        'examples': ['801456'],
        'extract': _make_label_extractor(['Account Number', 'Account #'], r'(\d{5,8})', max_lines=6),
    },
    'D&S Waste': {
        'has_account': True,
        'format': 'ACCT # NNNNNN or ACCT. # NNNNNN',
        'examples': ['316390', '413290'],
        'extract': _make_label_extractor(['ACCT #', 'ACCT. #', 'Account #'], r'(\d{5,7})', max_lines=4),
    },
    'Detroit Disposal': {
        'has_account': True,
        'format': 'Account Number NNNNNN',
        'examples': ['307901'],
        'extract': _make_label_extractor(['Account Number', 'Account #'], r'(\d{5,8})', max_lines=4),
    },
    'Lawrence Waste': {
        'has_account': True,
        'format': 'CUSTOMER NO. NNNN',
        'examples': ['9450'],
        'extract': _make_label_extractor(['CUSTOMER NO', 'Customer #'], r'(\d{3,6})', max_lines=6),
    },
    'Mid Valley Disposal': {
        'has_account': True,
        'format': 'Account Number NNNNNNN',
        'examples': ['3135452'],
        'extract': _make_label_extractor(['Account Number', 'Account #'], r'(\d{5,8})', max_lines=6),
    },
    'Waste Connections': {
        'has_account': True,
        'format': 'Account# NNNNNNN in table header, value in data row below',
        'examples': ['1082601', '321896557'],
        'extract': _make_label_extractor(['Account#', 'Account Number', 'Account #'], r'(\d{5,10})', max_lines=12),
    },
    'Patriot Waste': {
        'has_account': True,
        'format': 'Customer # NNNNNNNNNN',
        'examples': ['0000542004'],
        'extract': _make_label_extractor(['Customer #', 'Account #'], r'(\d{4,10})', max_lines=4),
    },
    'Waste Masters': {
        'has_account': True,
        'format': 'CUSTOMER NO. NNNN',
        'examples': ['8252'],
        'extract': _make_label_extractor(['CUSTOMER NO', 'Customer #'], r'(\d{3,6})', max_lines=6),
    },
    'C & D Disposal': {
        'has_account': True,
        'format': 'Account Number NN-NNNNNNNNN',
        'examples': ['97-00394043'],
        'extract': _make_label_extractor(['Account Number', 'Account #'], r'(\d{2}-\d{7,10})', max_lines=4),
    },
    'Coastal Waste': {
        'has_account': True,
        'format': 'Account Number: NNNNNNNNNN',
        'examples': ['7029187197'],
        'extract': _extract_coastal_waste_v2,
    },
    'Glendale Arizona Utilities': {
        'has_account': True,
        'format': 'ACCOUNT NUMBER: NNNNNNNN-NN',
        'examples': ['00321190-00'],
        'extract': _extract_glendale_az_utilities,
    },
    'Midwest Paper': {
        'has_account': True,
        'format': 'Account Number: NNNNNN-NNNN',
        'examples': ['003780-0000'],
        'extract': _make_label_extractor(['Account Number'], r'(\d{4,8}-\d{3,4})', max_lines=4),
    },
    'Texas Disposal': {
        'has_account': True,
        'format': 'Account #: N -NNNNNN N (spaces in number)',
        'examples': ['1-269891-5'],
        'extract': _extract_texas_disposal_v2,
    },
    'Tooele County Solid Waste': {
        'has_account': True,
        'format': 'CUSTOMER NO. NNNNN + ACCOUNT NNNNN-NNNNN',
        'examples': ['21073', '20112-21073'],
        'extract': _extract_tooele_county,
    },
    'All Waste': {
        'has_account': True,
        'format': 'Account #: N -NNNNNN N (same as Texas Disposal)',
        'examples': ['1-246108-2'],
        'extract': _extract_texas_disposal_v2,
    },
    'Cards KS': {
        'has_account': True,
        'format': 'Account No. NN-NNNNN N',
        'examples': ['21-37537-5'],
        'extract': _extract_texas_disposal_v2,
    },
    'Eco-Tech': {
        'has_account': True,
        'format': 'Acct Nbr: NNNNNNN',
        'examples': ['7918901'],
        'extract': _make_label_extractor(['Acct Nbr', 'Account #', 'Acct #'], r'(\d{5,8})', max_lines=4),
    },
    'Mountain State Waste': {
        'has_account': True,
        'format': 'ACCOUNT NNNNN',
        'examples': ['64975'],
        'extract': _make_label_extractor(['ACCOUNT', 'Account #'], r'(\d{4,8})', max_lines=4),
    },
    'Frontier Waste': {
        'has_account': True,
        'format': 'ACCOUNT NNNNNN',
        'examples': ['255959'],
        'extract': _make_label_extractor(['ACCOUNT', 'Account #'], r'(\d{5,8})', max_lines=4),
    },
    'WB Waste Solutions': {
        'has_account': True,
        'format': 'NNNNNNNNN (9-digit, no label)',
        'examples': ['150100615'],
        'extract': _extract_wb_waste,
    },
    'Intermountain Disposal': {
        'has_account': True,
        'format': 'Customer ID / Account code',
        'examples': ['LDS'],
        'extract': _extract_intermountain_disposal,
    },
    'Southern Sanitation': {
        'has_account': True,
        'format': 'CUSTOMER NO SS00213377 or 213377 WASTEOLOGY GROUP inline',
        'examples': ['SS00213377', '213377'],
        'extract': lambda text: (
            _make_label_extractor(['CUSTOMER NO', 'Customer #'], r'([A-Z]{2}\d{6,10})', max_lines=4)(text)
            or (lambda t: (m.group(1) if (m := re.search(r'(\d{5,8})\s+WASTEOLOGY', t.replace('\\n', '\n'), re.I)) else None))(text)
        ),
    },
    'Cavossa Disposal': {
        'has_account': True,
        'format': 'Cust ID: NNNNNN',
        'examples': ['133508'],
        'extract': _extract_cavossa_disposal,
    },
    'Star Waste': {
        'has_account': True,
        'format': 'ACCOUNT NUMBER ACNNNNT (OCR garbled)',
        'examples': ['AC8877T'],
        'extract': _extract_star_waste_v2,
    },
    'Direct Waste Services': {
        'has_account': True,
        'format': 'Account ID#: NNNN',
        'examples': ['4107'],
        'extract': _extract_direct_waste_v2,
    },
    'Nitti Sanitation': {
        'has_account': True,
        'format': 'CUSTOMER NO. in column header, value lines below',
        'examples': ['40599'],
        'extract': _make_label_extractor(['CUSTOMER NO', 'Customer #'], r'(\d{4,7})', max_lines=10),
    },
    'A1 INDUSTRIAL MAINTENANCE': {
        'has_account': True,
        'format': 'Account # NNNN (invoices only, work orders lack account)',
        'examples': ['3700'],
        'extract': _make_label_extractor(['Account #', 'Account Number'], r'(\d{3,8})', max_lines=8),
    },
    'All American Waste': {
        'has_account': True,
        'format': 'CustID NNNNNN',
        'examples': ['286046'],
        'extract': _make_label_extractor(['CustID', 'Cust ID', 'Customer #'], r'(\d{4,8})', max_lines=4),
    },
    'Blue Hen Dispose-All, Inc': {
        'has_account': True,
        'format': 'Customer Account No.: NNNNNN-NNNN',
        'examples': ['087817-0000'],
        'extract': _make_label_extractor(['Customer Account No', 'Account #'], r'(\d{5,8}-\d{3,4})', max_lines=4),
    },
    'County Hauling': {
        'has_account': True,
        'format': 'ACCOUNT NO. in column header, value lines below',
        'examples': ['181039'],
        'extract': _make_label_extractor(['ACCOUNT NO', 'Account #'], r'(\d{5,8})', max_lines=12),
    },
    'Northern Waste': {
        'has_account': True,
        'format': 'VENDOR ACCOUNT NUMBER multi-line',
        'examples': ['1003677582'],
        'extract': _extract_northern_waste_v2,
    },
    'Stericycle': {
        'has_account': True,
        'format': 'Customer No (Payer) NNNNNNNNNN',
        'examples': ['1000998553'],
        'extract': _extract_stericycle_v2,
    },
    'Valley Vista': {
        'has_account': True,
        'format': 'Account # multi-line',
        'examples': [],
        'extract': _extract_valley_vista_v2,
    },
    'Win Waste': {
        'has_account': True,
        'format': 'CUSTOMER NO. NN-NNNNN-NNNN',
        'examples': ['22-43984-0000'],
        'extract': _make_label_extractor(['CUSTOMER NO', 'Customer #'], r'(\d{2}-\d{5}-\d{4})', max_lines=4),
    },
    'Aspen Waste': {
        'has_account': True,
        'format': 'Account No. N-NNNNN N',
        'examples': ['1-50232-5'],
        'extract': _extract_texas_disposal_v2,
    },
    'Apex Waste': {
        'has_account': True,
        'format': 'ACCOUNT \\n DATE \\n NNNNNNNN or Customer: NNNNNNN/NAME',
        'examples': ['10185172', '3353191'],
        'extract': lambda text: (
            _make_label_extractor(['ACCOUNT', 'Account #', 'ACCOUNT #'], r'(\d{5,10})', max_lines=6)(text)
            or (lambda t: (m.group(1) if (m := re.search(r'Customer:\s*(\d{5,10})/', t.replace('\\n', '\n'))) else None))(text)
        ),
    },
}

# ============================================================
# GAP-015: PATTERN FIX ROUND — extractors for vendors identified
# in the vendor-level triage as PATTERN_FIX
# ============================================================


def _extract_recology_v4(text: str) -> Optional[str]:
    """Recology v4 — adds Statement/Invoice two-line header format.
    New formats (not in mar2026 _extract_recology_fixed):
      A. Statement Account\\nNumber Number\\n<13-digit> <10-digit>
      B. Invoice Invoice\\nAccount\\nDate Number Number\\n<date> <13-digit> <10-digit>
      C. Customer\\nNumber\\n<5-7 digit> (King County inline data row)
    Account is always the 10-digit number starting with 81 or 10.
    """
    normalized = text.replace('\\n', '\n')
    lines = normalized.split('\n')

    # Format A/B: "Number Number" header → data line with two large numbers
    for i, line in enumerate(lines):
        stripped = line.strip()
        if re.search(r'Number\s+Number', stripped):
            for j in range(i + 1, min(i + 4, len(lines))):
                matches = re.findall(r'\b(\d{7,13})\b', lines[j])
                if len(matches) >= 2:
                    # Account is the one starting with 81 or 10
                    for m in matches:
                        if m.startswith('81') or m.startswith('10'):
                            return m
                    # Fallback: return last match (account is typically second)
                    return matches[-1]
        # Also handle "Number\nNumber" on separate lines
        if stripped == 'Number' and i + 1 < len(lines) and lines[i + 1].strip() == 'Number':
            for j in range(i + 2, min(i + 5, len(lines))):
                matches = re.findall(r'\b(\d{7,13})\b', lines[j])
                if len(matches) >= 2:
                    for m in matches:
                        if m.startswith('81') or m.startswith('10'):
                            return m
                    return matches[-1]

    # Format C: Customer\nNumber\n<5-7 digit> OR date+invoice#+customer# data line
    for i, line in enumerate(lines):
        if line.strip() == 'Customer' and i + 1 < len(lines) and lines[i + 1].strip() == 'Number':
            for j in range(i + 2, min(i + 5, len(lines))):
                val = lines[j].strip()
                if re.match(r'^\d{5,7}$', val):
                    return val
                m = re.match(r'\d{2}/\d{2}/\d{4}\s+\d{10,13}\s+(\d{5,7})', val)
                if m:
                    return m.group(1)

    return None


def _extract_usa_waste_v2(text: str) -> Optional[str]:
    """USA Waste & Recycling — columnar OCR format.
    Layout: 'Account Number' on line 0, 'Invoice Number' on line 1,
    then vendor address block, then 5-7 digit account on its own line.
    """
    normalized = text.replace('\\n', '\n')
    lines = normalized.split('\n')

    for i, line in enumerate(lines):
        stripped = line.strip()
        if stripped == 'Account Number' and i + 1 < len(lines) and 'Invoice' in lines[i + 1]:
            # Value is 5-10 lines later (after address block)
            for j in range(i + 2, min(i + 12, len(lines))):
                val = lines[j].strip()
                if re.match(r'^\d{5,7}$', val):
                    return val
    return None


def _extract_greif_account(text: str) -> Optional[str]:
    """Greif — 5-digit customer number in Sold To / Ship-To block.
    OCR layout: Sold To\\nShip-To\\n60488\\nWASTEOLOGY...
    """
    normalized = text.replace('\\n', '\n')
    lines = normalized.split('\n')

    for i, line in enumerate(lines):
        if re.search(r'Ship.?To', line, re.I):
            for j in range(i + 1, min(i + 3, len(lines))):
                val = lines[j].strip()
                if re.match(r'^\d{4,6}$', val):
                    return val
    return None


def _extract_honolulu_disposal_v2(text: str) -> Optional[str]:
    """Honolulu Disposal — Past Due Notice format.
    Account embedded in Re: line: 'CUSTOMER_NAME - ACCOUNT_NUMBER'
    """
    normalized = text.replace('\\n', '\n')

    # Re: Past Due Notice\nCUSTOMER_NAME - NNNNNNNNNN
    m = re.search(r'Re:\s*Past\s*Due', normalized, re.I)
    if m:
        # Search next few lines for pattern ending with digits after dash
        pos = m.end()
        chunk = normalized[pos:pos + 200]
        m2 = re.search(r'-\s*(\d{7,10})', chunk)
        if m2:
            return m2.group(1)
    return None


def _extract_thomas_trash_v2(text: str) -> Optional[str]:
    """Thomas Trash — Account ID: MTK7N-32XHS (alphanumeric).
    """
    normalized = text.replace('\\n', '\n')
    m = re.search(r'Account\s*ID\s*:?\s*([A-Z0-9]{3,6}-[A-Z0-9]{3,6})', normalized, re.I)
    if m:
        return m.group(1).upper()
    # Multi-line: Account ID\nMTK7N-32XHS
    lines = normalized.split('\n')
    for i, line in enumerate(lines):
        if re.search(r'Account\s*ID', line, re.I):
            for j in range(i + 1, min(i + 3, len(lines))):
                val = lines[j].strip()
                if re.match(r'^[A-Z0-9]{3,6}-[A-Z0-9]{3,6}$', val, re.I):
                    return val.upper()
    return None


def _extract_best_way_v3(text: str) -> Optional[str]:
    """Best Way Disposal v3 — CUSTOMER NO header + 7-digit format.
    Also: Account # I-NNNNNN in rate letters.
    """
    normalized = text.replace('\\n', '\n')
    lines = normalized.split('\n')

    # CUSTOMER NO header → 7-digit value
    for i, line in enumerate(lines):
        if re.search(r'CUSTOMER\s*NO\b', line, re.I):
            for j in range(i + 1, min(i + 4, len(lines))):
                val = lines[j].strip()
                if re.match(r'^\d{6,8}$', val):
                    return val

    # Account # I-NNNNNN
    m = re.search(r'Account\s*#\s*:?\s*(I-\d{5,7})', normalized, re.I)
    if m:
        return m.group(1)

    return None


def _extract_cards_mo_v2(text: str) -> Optional[str]:
    """Cards Mo (Finocchio Brothers) — CUSTOMER # with 4-digit value.
    Remittance section: CUSTOMER #:\\nSITE #:\\n...\\n8631
    """
    normalized = text.replace('\\n', '\n')
    lines = normalized.split('\n')

    # CUSTOMER # label → scan for 3-5 digit value
    for i, line in enumerate(lines):
        if re.search(r'CUSTOMER\s*#', line, re.I):
            for j in range(i + 1, min(i + 6, len(lines))):
                val = lines[j].strip()
                if re.match(r'^\d{3,6}$', val):
                    return val

    return None


def _extract_timmons_v2(text: str) -> Optional[str]:
    """Timmons Waste Service (Oak Ridge Hauling) — Customer Number with NN-NNNNNNN format.
    """
    normalized = text.replace('\\n', '\n')

    # Inline: Customer Number: 01-5004624 1
    m = re.search(r'Customer\s*Number\s*:?\s*(\d{2}-\d{5,8}\s*\d?)', normalized, re.I)
    if m:
        return m.group(1).strip()

    # Multi-line
    lines = normalized.split('\n')
    for i, line in enumerate(lines):
        if re.search(r'Customer\s*Number', line, re.I):
            for j in range(i + 1, min(i + 3, len(lines))):
                val = lines[j].strip()
                m2 = re.match(r'^(\d{2}-\d{5,8}\s*\d?)$', val)
                if m2:
                    return m2.group(1).strip()
    return None


def _extract_ace_recycling_v4(text: str) -> Optional[str]:
    """Ace Recycling v4 — adds CR&R Account Number NN-NNNNNNN N format.
    Some Ace Recycling-detected invoices are actually CR&R invoices.
    """
    normalized = text.replace('\\n', '\n')
    lines = normalized.split('\n')

    # CR&R format: Account Number → NN-NNNNNNN N
    for i, line in enumerate(lines):
        if re.search(r'Account\s*Number', line, re.I):
            for j in range(i + 1, min(i + 4, len(lines))):
                val = lines[j].strip()
                m = re.match(r'^(\d{2}-\d{7}\s*\d?)$', val)
                if m:
                    return m.group(1).strip()
    # Also try inline
    m = re.search(r'Account\s*Number\s*:?\s*(\d{2}-\d{7}\s*\d)', normalized, re.I)
    if m:
        return m.group(1).strip()

    return None


def _extract_rumpke_v2(text: str) -> Optional[str]:
    """Rumpke v2 — adds GS-prefix customer numbers (Haul It Away division).
    Format: Customer #: GS01586757
    """
    normalized = text.replace('\\n', '\n')
    # GS prefix + 8 digits
    m = re.search(r'(?:Customer|Cust)\s*#\s*:?\s*(GS\d{6,10})', normalized, re.I)
    if m:
        return m.group(1)
    return None


def _extract_burrtec_v2(text: str) -> Optional[str]:
    """Burrtec v2 — unlabeled NN-XX NNNNNN format at start of invoice.
    """
    normalized = text.replace('\\n', '\n')
    # NN-XX NNNNNN followed by date
    m = re.search(r'(\d{2}-[A-Z]{2}\s*\d{6})\s*\n\s*\d{2}/\d{2}/\d{2}', normalized)
    if m:
        return m.group(1)
    return None


# Add GAP-015 vendor entries to the main dict
_GAP015_VENDOR_ADDITIONS = {
    'Greif': {
        'has_account': True,
        'format': '5-digit in Sold To block',
        'examples': ['60488'],
        'extract': _extract_greif_account,
    },
    'Thomas Trash': {
        'has_account': True,
        'format': 'Account ID: XXXXX-XXXXX (alphanumeric)',
        'examples': ['MTK7N-32XHS'],
        'extract': _extract_thomas_trash_v2,
    },
    'Cards Mo': {
        'has_account': True,
        'format': 'CUSTOMER # NNNN',
        'examples': ['8631'],
        'extract': _extract_cards_mo_v2,
    },
    'DC Waste': {
        'has_account': True,
        'format': 'Customer # NNNNN or Account Number NNNNN',
        'examples': ['72308'],
        'extract': _make_label_extractor(
            ['Customer #', 'CUSTOMER #', 'Account Number', 'ACCOUNT NUMBER'],
            r'(\d{4,7})', max_lines=4),
    },
    'Mid Valley Disposal': {
        'has_account': True,
        'format': 'Account Number NNNNNN',
        'examples': [],
        'extract': _make_label_extractor(
            ['Account Number', 'Account #', 'ACCOUNT'],
            r'(\d{4,8})', max_lines=4),
    },
    'CLAY COUNTY REFUSE TAX OFFICE': {
        'has_account': True,
        'format': 'Account# NNNNNNNNNN',
        'examples': ['4091219402'],
        'extract': _make_label_extractor(
            ['Account', 'ACCOUNT', 'Account #'],
            r'(\d{8,12})', max_lines=4),
    },
    'Innovate Crushing and Aggregate, Inc': {
        'has_account': True,
        'format': 'Customer# NNNN',
        'examples': ['1186'],
        'extract': _make_label_extractor(
            ['Customer', 'Customer #', 'CUSTOMER'],
            r'(\d{3,6})', max_lines=4),
    },
}

# Merge GAP-015 entries: new vendors get added directly,
# existing vendors get the new extractor as an additional fallback.
for _v, _e in _GAP015_VENDOR_ADDITIONS.items():
    if _v not in VENDOR_ADDITIONS_MAR2026_V93D:
        VENDOR_ADDITIONS_MAR2026_V93D[_v] = _e
    else:
        _existing = VENDOR_ADDITIONS_MAR2026_V93D[_v]
        _existing_fn = _existing.get('extract')
        _new_fn = _e.get('extract')
        if _existing_fn and _new_fn and _existing.get('has_account', True):
            VENDOR_ADDITIONS_MAR2026_V93D[_v] = {
                **_existing,
                'extract': lambda text, f1=_existing_fn, f2=_new_fn: f1(text) or f2(text),
            }

# GAP-015: Vendors needing combined extractors (existing v93d + new fallback)
# These are added to V93D_EXPLICIT_OVERRIDES so the combined function replaces base entirely.
_gap015_existing_vendor_fixes = {
    'Recology': _extract_recology_v4,
    'USA Waste': _extract_usa_waste_v2,
    'Rumpke': _extract_rumpke_v2,
    'Ace Recycling': _extract_ace_recycling_v4,
    'Honolulu Disposal': _extract_honolulu_disposal_v2,
    'Burrtec': _extract_burrtec_v2,
    'Best Way Disposal': _extract_best_way_v3,
    'Timmons Waste Service': _extract_timmons_v2,
}
for _v, _new_fn in _gap015_existing_vendor_fixes.items():
    if _v in VENDOR_ADDITIONS_MAR2026_V93D:
        # Vendor already in v93d — combine existing + new as fallback
        _existing = VENDOR_ADDITIONS_MAR2026_V93D[_v]
        _existing_fn = _existing.get('extract')
        if _existing_fn:
            VENDOR_ADDITIONS_MAR2026_V93D[_v] = {
                **_existing,
                'extract': lambda text, f1=_existing_fn, f2=_new_fn: f1(text) or f2(text),
            }
    else:
        # Vendor NOT in v93d — add as new entry (will be combined with base/mar2026 by main engine)
        VENDOR_ADDITIONS_MAR2026_V93D[_v] = {
            'has_account': True,
            'format': 'GAP-015 fallback pattern',
            'examples': [],
            'extract': _new_fn,
        }

# Merge round 3 entries WITHOUT overwriting original v93d entries.
# For vendors already in the dict, combine: original tries first, round 3 as fallback.
# This prevents regressions where round 3 edge-case extractors replace broader originals.
for _r3_vendor, _r3_entry in _ROUND3_VENDOR_ADDITIONS.items():
    if _r3_vendor not in VENDOR_ADDITIONS_MAR2026_V93D:
        # Brand new vendor — add directly
        VENDOR_ADDITIONS_MAR2026_V93D[_r3_vendor] = _r3_entry
    else:
        # Vendor already in v93d — combine original + round 3 as fallback
        _orig_entry = VENDOR_ADDITIONS_MAR2026_V93D[_r3_vendor]
        _orig_fn = _orig_entry.get('extract')
        _r3_fn = _r3_entry.get('extract')
        if _orig_fn and _r3_fn and _orig_entry.get('has_account', True):
            VENDOR_ADDITIONS_MAR2026_V93D[_r3_vendor] = {
                **_orig_entry,  # keep original metadata
                'extract': lambda text, f1=_orig_fn, f2=_r3_fn: f1(text) or f2(text),
            }


# ----------------------------------------------------------
# NO_ACCOUNT VENDORS (confirmed no customer account numbers)
# ----------------------------------------------------------

_NO_ACCOUNT_VENDORS_V93D = [
    # From detailed OCR review (no_pattern vendors)
    'RMR Consolidated',       # Remittance advices, not invoices
    'Wasteology',             # Misdetected internal docs / Marion County bills
    'Triple H Disposal',
    'PROWARE WASTE AND RECYCLING EQUIPMENT',
    'FLAT CREEK SOLUTIONS',
    'Affordable Waste Solutions',
    'ARG TRANSFER & RECYCLING',
    'Total Recycling and Waste Solutions',
    'WASTE SOLUTIONS',
    'SURPLUS RECYCLING',
    'Consolidated Industrial Services',
    'DAVIS SEPTICS & BACKHOE, INC',
    'Peak Waste, LLC',
    'Emfinger Steel Company',
    'Secrest Disposal Co',
    'Greenway Shredding and Recycling',
    'RMR Atlanta',
    'MILLENNIUM CONTAINER SERVICE',
    'S & S METALS',
    '4G',
    'ALLAN COMPANY',
    'Anytime Portables, Inc',
    'Bakersfield Recycling Services Inc',
    'BERMAN BROS., INC',
    'California Recyclers',
    'Cocolamus Creek Disposal Service',
    'Fox Works LLC, Trash Services',
    'Action Welding Inc',
    'Dynamic Waste Company',
    'West Georgia Sanitation',
    'City of Arkadelphia',
    'CONTROL Rubbage',
    'INDUSTRIAL REFURISHMENT LLC',
    'S & S Scrap Metal Inc',
    'Anclote Metal Recycling',
    'Bay Area dumpster rental',
    'Bill Floyd Services',
    'Bolk Dumpster LLC',
    'CENTRAL ILLINOIS DISPOSAL',
    'Kienbaum Iron & Metal LLC',
    'Sunbelt Environmental Services',
    'BALER & COMPACTOR HYDRAULIC',
    'BUCHANAN COUNTY SANITATION DEPT',
    'CP Manages, LLC',
    'CPM Recycling Services Inc',
    'DP Joyner Industrial LLC',
    'GENTRY Trash',
    'ALL WASTE',
    'Capital Electric',
    'COMMON GROUND COMPOST',
    'IDAWY SOLID WASTE DISTRICT',
    'Portable toilets-Storage containers',
    'Signature Dumpster Rentals',
    'ZEMKE ROLL-OFF SERVICE',
    'A. C. KREBS COMPANY',
    'Abyss Rising LLC',
    'ACP-30 Dumpster Service LLC',
    'ALWAYS BUYING SCRAP!',
    'arko Metals, Inc',
    'Blaine Street Partners',
    'CAL-WASTE',
    'CARAUSTAR RECYCLING SALEM',
    'Wastequip',
    # From UNCERTAIN → NO_ACCOUNT
    'Elite Roll-Off Solutions',
    "RAY'S DEMOLITION LLC",
    'SAFEGUARD BUSINESS SYSTEMS',
    'WRS Waste Recycling Service',
    'adaptecsolutions',
    'Gary\'s Garbage Services',
    "Bud's Clean Up Service",
    # From corpus analysis — 22 vendors with 0 account-like labels in OCR
    'CHOCTAW COUNTY WASTE SERVICES',  # Municipal, no account
    'CAROLINA COMMERCIAL & INDUSTRIAL REFURISHMENT LLC',  # No account
    'Cyclyx International LLC',  # Recycling, no account labels
    'ALLIANCE INDUSTRIAL CORP',  # Industrial, no account
    'automotive recyclers association',  # Association, no account
    'Ace Container - WP',        # Container service, no account
    'City of Arkadelphia Sanitation Department',  # Municipal sanitation
    'Reddy Equipment Inc.',      # Equipment vendor, no account
    'American Metal and Paper',  # Recycling, no account labels
    'Bay Area dumpster rental and junk removal',  # Rental, no account
    'Elite Roll-Off Solutions LLC',  # Roll-off rental
    'MID-NEBRASKA DISPOSAL, INC',    # No account labels
    'Sunbelt Environmental Services Inc.',  # No account labels
    # From Step 3 review grind — round 2 (2026-03-11)
    'All American Disposal',     # Small hauler (Hennepin, IL) — no customer account field
    # Round 3 — NO_ACCOUNT confirmations from review grind
    'AAA citishred',              # Shredding service invoices, no account field
    'The Good Guys',              # Payment receipts (Earthwise Enterprise), no account
    # Re-added after audit: base engine has extractor but >60% failure rate = genuinely NO_ACCOUNT
    'Local Waste Solution',       # 0/32 extracted (100% fail) — base extractor broken
    'Dedicated Dumpster Service',  # 2/34 (94% fail)
    'Waste Away',                  # 33/191 (83% fail) — mostly no-account invoices
    'Mills Brothers',              # 13/51 (75% fail)
    'C&C Disposal',                # 6/22 (73% fail)
    'Waste Services LLC',          # 41/146 (72% fail)
    # NOTE: 53 vendors removed from NO_ACCOUNT — had working extractors in base/additions
    # See GAP-014 in PROCESS_GAPS.md for full list
    # GAP-015: Vendor-level triage — ONLY vendors with 0% extraction rate
    # NOTE: 11 vendors originally classified as NO_ACCOUNT here were REMOVED because
    # they had working extractors (73-99.6% extraction rate). Only the MAYBE_NO_ACCOUNT
    # vendors below (all at 0% extraction) are genuinely NO_ACCOUNT.
    # MAYBE_NO_ACCOUNT (confirmed from vendor summary triage)
    'AWS- Affordable Waste Services',
    'AWS- Affordable waste Services',
    'Advanced Global Communications, Inc',
    'Advanced Intralogistics LLC',
    'ASC, LLC',
    'Basin junk removal LLC',
    'Black Bear Composting',
    'CHOCTAW COUNTY, WASTE SERVICES',
    'Elite Metal Performance, LLC',
    'GATEWAY RECYCLING',
    "George's Salvage Co",
    'Portable toilets-Storage containers-Trash containers',
    'Superior Waste',
    'Zero Waste',
]

for _vendor in _NO_ACCOUNT_VENDORS_V93D:
    VENDOR_ADDITIONS_MAR2026_V93D[_vendor] = {
        'has_account': False,
        'format': None,
        'examples': [],
        'extract': lambda x: None,
    }

# ============================================================
# EXPLICIT OVERRIDES — vendors with debugged improvements that
# SHOULD replace existing base/addition entries. Everything else
# in VENDOR_ADDITIONS_MAR2026_V93D only applies to new vendors.
# ============================================================
V93D_EXPLICIT_OVERRIDES = {
    # Improved extraction functions (top extraction_failed vendors)
    'Wasatch Waste',          # .NNNNN format + multi-line
    'Robinson Waste',         # v3: Customer: NNNNNN + issue ticket skip
    'Burrtec',                # Extended range(i+8) for column-header layout
    'Western Elite',          # \\n normalization + multi-line search
    'GFL',                    # Dash format (VM-1372)
    'Tower Compactor',        # Extended to i+6 range
    'Capital Waste',          # CUSTOMER NO. label variant
    'Rumpke',                 # 8-10 digit range
    'Walker Lake Disposal',   # \\n normalization
    'FCC Environmental',      # v2: multi-line + ACCOUNT # + expanded range
    'LRS',                    # Customer No column-header layout
    'Miami-Dade DSWM',        # Customer Number / Account Number
    'EOMS Recycling',             # v93d broadens ID# from 12-digit to 4-12 digit
    'Timmons Waste Service',      # TrashBilling ID# (not in base)
    'Anytime Waste',              # NavuSoft + WM National Account format
    'Waste Pro',                  # v2: BRT format 02-0201795 0 + short numeric
    'Live Oak',                   # v2: Acct# inline + CUSTOMER NO + label fallback
    # NO_ACCOUNT overrides (confirmed no accounts in this corpus)
    *_NO_ACCOUNT_VENDORS_V93D,
    # Round 3 — NEW vendors only (no existing pattern to break)
    'DISPOSAL & RECYCLING INC. Aloha, OR 97006',
    'ENVIROTECH WASTE SERVICES',
    'Royal Carting Service',
    'WASTEQUIP',
    'Alamo Disposal',
    'ADA County',
    'City of Riverton',
    'Emergency Sanitation Deployment LLC DBA',
    'Floaters Portable Sanitation',
    'Hopkinsville Solid Waste Enterprise',
    'A-1 INDUSTRIAL MAINTENANCE, INC',
    # Round 3 — existing vendors where v93d REPLACES base (only truly new formats)
    'Glendale Arizona Utilities',   # backward label format, base can't handle
    'Star Waste',                   # OCR garbled spacing, base can't handle
    'Direct Waste Services',        # Account ID# label, base doesn't use
    # GAP-015 — ONLY truly new vendors (no existing base extractor)
    'CLAY COUNTY REFUSE TAX OFFICE', # Account# 10-digit (new vendor)
    'Innovate Crushing and Aggregate, Inc', # Customer# 4-digit (new vendor)
    # NOTE: All other GAP-015 vendors use default combine (base first, v93d fallback).
    # Do NOT add vendors here that have working base extractors — it replaces them.
}
