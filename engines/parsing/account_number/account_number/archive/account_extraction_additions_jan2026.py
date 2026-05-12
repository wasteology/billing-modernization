"""
Account Number Extraction Additions - January 2026
Additional vendor patterns for 0% extraction vendors identified through account_linkage analysis.

To integrate: Import and merge VENDOR_ADDITIONS into the main VENDOR_ACCOUNTS dict.

Coverage target: ~203 vendors with 0% extraction, ~20,000 invoices
"""
import re
from typing import Optional


# ============================================================
# EXTRACTION FUNCTIONS
# ============================================================

def _extract_standard_waste(text: str) -> Optional[str]:
    """Format: Account ID followed by site code (UPS.NJEDI1, UPS.NJSBR)
    Note: ~50% of invoices are scale tickets without account IDs
    """
    m = re.search(r'Account\s*ID\s+([A-Z]{2,5}\.[A-Z0-9]{3,10})', text, re.I)
    if m:
        return m.group(1).upper()
    # Try with literal \n
    m = re.search(r'Account\s*ID\\n([A-Z]{2,5}\.[A-Z0-9]{3,10})', text, re.I)
    return m.group(1).upper() if m else None


def _extract_all_american_waste(text: str) -> Optional[str]:
    """Format: ACCOUNT # followed by 6-digit number"""
    m = re.search(r'ACCOUNT\s*#\s*(\d{6})', text)
    return m.group(1) if m else None


def _extract_pete_pete(text: str) -> Optional[str]:
    """Format: Account No: 7-digit from scale tickets (Rumpke, WM)"""
    m = re.search(r'Account\s*No\s*:\s*(\d{7})', text, re.I)
    if m:
        return m.group(1)
    # Also try SoftPak ID format: 38 0000044 -> 380000044
    m = re.search(r'SoftPak\s*ID\s*:\s*(\d{2})\s*(\d{7})', text, re.I)
    return m.group(1) + m.group(2) if m else None


def _extract_becker360(text: str) -> Optional[str]:
    """Format: Service Location: UPS-MOAPP, UPS-KYBOW"""
    m = re.search(r'Service\s*Location:\s*([A-Z]{2,5}-[A-Z]{2}[A-Z0-9]{2,6})', text, re.I)
    return m.group(1).upper() if m else None


def _extract_specific_waste(text: str) -> Optional[str]:
    """Format: Company ID: aspec110854"""
    m = re.search(r'Company\s*ID:\s*([a-z]+\d+)', text, re.I)
    return m.group(1).lower() if m else None


def _extract_waste_path(text: str) -> Optional[str]:
    """Format: Account #: 471-010"""
    m = re.search(r'Account\s*#[:\s]*(\d{3}-\d{3})', text, re.I)
    return m.group(1) if m else None


def _extract_city_of_boise(text: str) -> Optional[str]:
    """Format: 15-digit account number"""
    m = re.search(r'Account\s*#[:\s]*(\d{15})', text, re.I)
    return m.group(1) if m else None


def _extract_wise_environmental(text: str) -> Optional[str]:
    """Format: 6-digit account number near top of invoice
    OCR structure: Invoice#, Company, Amount, AccountNum, Address...
    """
    # Account number appears early, before ACCOUNT # label
    # Pattern: \n followed by 6-digit number before "PO Box"
    m = re.search(r'\\n(\d{6})\\n(?:PO\s*Box|[A-Z][a-z]+)', text)
    if m:
        return m.group(1)
    # Fallback: look for 6-digit after amount
    m = re.search(r'\d+\.\d{2}\\n(\d{6})\\n', text)
    return m.group(1) if m else None


def _extract_stryker_environmental(text: str) -> Optional[str]:
    """Format: Wasteology:UPS-Mebane in Bill To section"""
    m = re.search(r'Wasteology:([A-Z]{2,5}-[A-Za-z]+)', text)
    return m.group(1).upper() if m else None


def _extract_las_vegas_recycling(text: str) -> Optional[str]:
    """Format: Job Number#: 8-digit"""
    m = re.search(r'Job\s*Number#:\s*(\d{8})', text)
    return m.group(1) if m else None


def _extract_redbox_plus(text: str) -> Optional[str]:
    """Format: Account Id: WA-2308-9398"""
    m = re.search(r'Account\s*Id:\s*([A-Z]{2}-\d{4}-\d{4})', text, re.I)
    return m.group(1).upper() if m else None


def _extract_howard_disposal(text: str) -> Optional[str]:
    """Format: Project with D-NNNN or just NNNN location code"""
    m = re.search(r'Project\\n(?:D-)?(\d{4})\s', text, re.I)
    if m:
        return f'D-{m.group(1)}'
    m = re.search(r'Project\\n[A-Za-z\s]+-\s*(\d{4})', text)
    return f'D-{m.group(1)}' if m else None


def _extract_cri_curbside(text: str) -> Optional[str]:
    """NO_ACCOUNT - Invoice-only vendor, no customer account numbers"""
    return None


def _extract_boyas_recycling(text: str) -> Optional[str]:
    """NO_ACCOUNT - Uses PO numbers only, no customer account"""
    return None


def _extract_rocky_ridge(text: str) -> Optional[str]:
    """NO_ACCOUNT - Invoice-only vendor"""
    return None


def _extract_community_disposal(text: str) -> Optional[str]:
    """Format: CBRE-UPS-XXXXX in Bill To section"""
    # Pattern: (CBRE-UPS-FLJAC) in Bill To
    m = re.search(r'\(([A-Z]{2,5}-[A-Z]{2,5}-[A-Z]{2,5})\)', text)
    if m:
        return m.group(1)
    # Fallback: Just CBRE-UPS-XXX pattern
    m = re.search(r'([A-Z]{2,5}-[A-Z]{2,5}-[A-Z]{2,5})', text)
    return m.group(1) if m else None


def _extract_trash_taxi(text: str) -> Optional[str]:
    """Format: ID#: 12-digit TrashBilling customer ID"""
    m = re.search(r'ID#:\s*(\d{12})', text)
    if m:
        return m.group(1)
    # Also try Customer Information followed by number
    m = re.search(r'Customer\s*Information\\n(\d{12})', text)
    return m.group(1) if m else None


def _extract_heavenly_trash(text: str) -> Optional[str]:
    """NO_ACCOUNT - Invoice-only vendor"""
    return None


def _extract_conigliaro(text: str) -> Optional[str]:
    """NO_ACCOUNT - Uses work order numbers only"""
    return None


def _extract_premier_waste(text: str) -> Optional[str]:
    """NO_ACCOUNT - Invoice-only vendor"""
    return None


def _extract_grizzly_disposal(text: str) -> Optional[str]:
    """Format: ID#: 12-digit TrashBilling customer ID"""
    m = re.search(r'ID#:\s*(\d{12})', text)
    if m:
        return m.group(1)
    # Also try Customer Information followed by number
    m = re.search(r'Customer\s*Information\\n(\d{12})', text)
    return m.group(1) if m else None


def _extract_wompost(text: str) -> Optional[str]:
    """NO_ACCOUNT - Multiple document types, no consistent account pattern"""
    return None


# TrashBilling platform vendors - all use ID#: 12-digit format
def _extract_trashbilling_id(text: str) -> Optional[str]:
    """Generic TrashBilling ID extraction - 12-digit customer ID"""
    m = re.search(r'ID#:\s*(\d{12})', text)
    if m:
        return m.group(1)
    m = re.search(r'Customer\s*Information\\n(\d{12})', text)
    return m.group(1) if m else None


def _extract_rdt_inc(text: str) -> Optional[str]:
    return _extract_trashbilling_id(text)


def _extract_dependable_sanitation(text: str) -> Optional[str]:
    return _extract_trashbilling_id(text)


def _extract_hill_country_waste(text: str) -> Optional[str]:
    return _extract_trashbilling_id(text)


def _extract_hart_sanitation(text: str) -> Optional[str]:
    return _extract_trashbilling_id(text)


def _extract_reliable_sanitation(text: str) -> Optional[str]:
    return _extract_trashbilling_id(text)


def _extract_thompson_sanitation(text: str) -> Optional[str]:
    return _extract_trashbilling_id(text)


def _extract_disposal_services_llc(text: str) -> Optional[str]:
    return _extract_trashbilling_id(text)


# Other vendor-specific patterns
def _extract_ej_harrison(text: str) -> Optional[str]:
    """Format: ACCOUNT# N-NNNNNNNN (OCR may add spaces)"""
    # Clean OCR spacing: "3 -0032020 5" -> "3-00320205"
    m = re.search(r'ACCOUNT#\s*(\d)\s*-?\s*(\d[\d\s]{6,9})', text, re.I)
    if m:
        # Remove internal spaces from account number
        acct = m.group(1) + '-' + m.group(2).replace(' ', '')
        return acct
    return None


def _extract_first_piedmont(text: str) -> Optional[str]:
    """Format: ACCOUNT NO: 7-digit"""
    m = re.search(r'ACCOUNT\s*NO:\s*\\n?(\d{7})', text, re.I)
    if m:
        return m.group(1)
    # Fallback: in service address line
    m = re.search(r'\\n(\d{7})\\n.*?Commonwealth|Industrial|\\d{5}', text)
    return m.group(1) if m else None


def _extract_lawrence_county(text: str) -> Optional[str]:
    """Format: Customer No: NNN or NNNNNNNN"""
    m = re.search(r'Customer\s*No:\s*\\n?(\d{3,8})', text, re.I)
    if m:
        acct = m.group(1)
        # Pad to 8 digits if needed
        return acct.zfill(8) if len(acct) < 8 else acct
    return None


def _extract_northern_waste(text: str) -> Optional[str]:
    """Format: CUSTOMER NO followed by 6-digit number"""
    m = re.search(r'CUSTOMER\s*NO\s*\\n(\d{6})', text, re.I)
    return m.group(1) if m else None


def _extract_green_guys(text: str) -> Optional[str]:
    """NO_ACCOUNT - Payment receipts only, no customer account numbers"""
    return None


# ============================================================
# BATCH 2 - Additional vendor patterns from Jan 2026 analysis
# ============================================================

def _extract_aces_disposal(text: str) -> Optional[str]:
    """Format: Customer ID: NN-NNNNN-NNNNN (WM invoices)"""
    m = re.search(r'Customer\s*ID:\s*\\n?(\d{2}-\d{5}-\d{5})', text, re.I)
    return m.group(1) if m else None


def _extract_solid_waste_authority(text: str) -> Optional[str]:
    """Format: CUSTOMER NO RSA001938 (3-letter prefix + 6 digits)"""
    m = re.search(r'CUSTOMER\s*NO\s*\\n?([A-Z]{3}\d{6})', text, re.I)
    return m.group(1).upper() if m else None


def _extract_clean_slate(text: str) -> Optional[str]:
    """Format: Header row (Invoice #:\\nAccount #:\\n...) then value row
    Values appear after all headers: Invoice#, Account#, PaymentDate, PaymentMethod
    """
    # Pattern: Account #:\n...values...\n5-digit account
    m = re.search(r'Invoice\s*#:\\nAccount\s*#:\\n.*?\\n(\d{5})\\n\d{5}\\n', text, re.I)
    if m:
        return m.group(1)
    # Fallback: look for 5-digit after Account #:
    m = re.search(r'Account\s*#:\\n.*?\\n(\d{5})\\n', text, re.I)
    return m.group(1) if m else None


def _extract_corporate_services(text: str) -> Optional[str]:
    """Format: Customer No. in header, value T022570 appears after other header values"""
    # Pattern: Customer No.\n...then later...\nT######\n
    m = re.search(r'Customer\s*No\.\\n.*?\\n([A-Z]\d{6})\\n', text, re.I)
    if m:
        return m.group(1).upper()
    # Alternative: just find T###### pattern directly
    m = re.search(r'\\n([A-Z]\d{6})\\n', text)
    return m.group(1).upper() if m else None


def _extract_bruin_waste(text: str) -> Optional[str]:
    """Format: CUSTOMER NO in header row, 6-digit value in value row
    Header: CUSTOMER NO\\nINVOICE DATE\\n...
    Values: 790552\\nAug 30...
    """
    m = re.search(r'CUSTOMER\s*NO\\nINVOICE\s*DATE\\n.*?\\n(\d{6})\\n', text, re.I)
    if m:
        return m.group(1)
    # Fallback: look for QUICK PAY CODE followed by values
    m = re.search(r'QUICK\s*PAY\s*CODE\\n(\d{6})\\n', text, re.I)
    return m.group(1) if m else None


def _extract_roosevelt_ut(text: str) -> Optional[str]:
    """Format: ACCOUNT NO. NN-NNNN-NN"""
    m = re.search(r'ACCOUNT\s*NO\.\s*[►\s]*\\n.*?\\n(\d{2}-\d{4}-\d{2})', text, re.I)
    if m:
        return m.group(1)
    # Direct pattern
    m = re.search(r'(\d{2}-\d{4}-\d{2})', text)
    return m.group(1) if m else None


def _extract_texas_pride(text: str) -> Optional[str]:
    """Format: Header row then values
    Invoice Date\\nInvoice Number\\nCustomer Number\\nDue Date\\n
    12/10/2025\\n2061216\\n10-79392 6\\n01/02/2026\\n
    """
    # Match Customer Number in headers, then find NN-NNNNN N pattern in values
    m = re.search(r'Customer\s*Number\\nDue\s*Date\\n[\d/]+\\n\d+\\n(\d{2}-\d{5})\s*(\d)', text, re.I)
    if m:
        return m.group(1) + m.group(2)
    # Direct pattern for NN-NNNNN followed by single digit
    m = re.search(r'\\n(\d{2}-\d{5})\s+(\d)\\n', text)
    if m:
        return m.group(1) + m.group(2)
    return None


def _extract_city_of_jackson(text: str) -> Optional[str]:
    """Format: CUSTOMER NAME\\nCUSTOMER NO.\\nSERVICE LOCATION\\n
    then values: NAME\\n7278319\\nADDRESS\\n
    """
    m = re.search(r'CUSTOMER\s*NO\.\\nSERVICE\s*LOCATION\\n[^\\]+\\n(\d{7})\\n', text, re.I)
    if m:
        return m.group(1)
    # Direct pattern: 7-digit between service address info
    m = re.search(r'\\n(\d{7})\\n\d{3}\s+[A-Z]', text)
    return m.group(1) if m else None


def _extract_aaa_disposal(text: str) -> Optional[str]:
    """Format: NN- NNNNNN or NN-NNNNNN"""
    m = re.search(r'(\d{2})-?\s*(\d{6})\s*\d?\s*\\n', text)
    if m:
        return m.group(1) + '-' + m.group(2)
    return None


def _extract_southern_sanitation(text: str) -> Optional[str]:
    """Format: INVOICE NO.\\nPAGE\\nDATE\\nCUSTOMER NO.\\nREFERENCE NO.\\n
    Values: 0000230597\\n1\\n12/01/2025\\n210405\\n
    Customer NO is 4th value
    """
    # Pattern: CUSTOMER NO.\nREFERENCE in headers, then 6-digit after date
    m = re.search(r'CUSTOMER\s*NO\.\\nREFERENCE.*?\\n\d+\\n\d\\n[\d/]+\\n(\d{6})\\n', text, re.I)
    if m:
        return m.group(1)
    # Alternative: find 6-digit after date pattern
    m = re.search(r'\\n\d{2}/\d{2}/\d{4}\\n(\d{6})\\n', text)
    return m.group(1) if m else None


# NO_ACCOUNT vendors from batch 2
def _extract_walker_lake(text: str) -> Optional[str]:
    """NO_ACCOUNT - Uses simple customer numbers in parens, not reliable"""
    return None


def _extract_curbside(text: str) -> Optional[str]:
    """NO_ACCOUNT - Uses work order numbers"""
    return None


def _extract_specialty_pallet(text: str) -> Optional[str]:
    """NO_ACCOUNT - Sales orders/BOL, uses PO numbers"""
    return None


def _extract_conex_recycling(text: str) -> Optional[str]:
    """NO_ACCOUNT - Invoice-only vendor"""
    return None


def _extract_five_star_waste(text: str) -> Optional[str]:
    """NO_ACCOUNT - Uses PO numbers only"""
    return None


def _extract_total_reclaim(text: str) -> Optional[str]:
    """NO_ACCOUNT - Uses SO/Order numbers only"""
    return None


def _extract_pennohio(text: str) -> Optional[str]:
    """NO_ACCOUNT - Uses service location refs"""
    return None


def _extract_advance_machine(text: str) -> Optional[str]:
    """NO_ACCOUNT - Equipment service invoices"""
    return None


def _extract_d_crescio(text: str) -> Optional[str]:
    """NO_ACCOUNT - Text-based customer IDs (Wasteology-BOA)"""
    return None


def _extract_all_metals_recycling(text: str) -> Optional[str]:
    """NO_ACCOUNT - Uses location codes (VTBAR)"""
    return None


def _extract_southern_illinois_waste(text: str) -> Optional[str]:
    """NO_ACCOUNT - Uses location/PO numbers"""
    return None


# ============================================================
# BATCH 3 - Additional vendor patterns from Jan 2026 analysis
# ============================================================

def _extract_greif(text: str) -> Optional[str]:
    """Format: Supplier Number followed by 9-digit"""
    m = re.search(r'Supplier\s*Number\\n.*?\\n(\d{9})\\n', text, re.I)
    if m:
        return m.group(1)
    m = re.search(r'\\n(\d{9})\\n\d{2}-\d{2}-\d{4}', text)
    return m.group(1) if m else None


def _extract_miami_dade_dswm(text: str) -> Optional[str]:
    """Format: Account Number 7-digit (Great Waste format)"""
    m = re.search(r'Account\s*Number\\n.*?Date\\n(\d{7})\\n', text, re.I)
    if m:
        return m.group(1)
    m = re.search(r'Account\s*Number\\n(\d{7})\\n', text, re.I)
    return m.group(1) if m else None


def _extract_pellitteri(text: str) -> Optional[str]:
    """Two formats:
    1. Statement: Account #:\n17966800\n
    2. Invoice: Account Number\nInvoice Date\n18859300\n
    """
    # Statement format
    m = re.search(r'Account\s*#:\s*\\n?(\d{8})', text, re.I)
    if m:
        return m.group(1)
    # Invoice format: Account Number header followed by value
    m = re.search(r'Account\s*Number\\nInvoice\s*Date\\n(\d{8})\\n', text, re.I)
    return m.group(1) if m else None


def _extract_penn_waste(text: str) -> Optional[str]:
    """Format: Account Number: PC + 6 digits"""
    m = re.search(r'Account\s*Number:\\n.*?\\n(PC\d{6})', text, re.I)
    if m:
        return m.group(1).upper()
    m = re.search(r'\\n(PC\d{6})\\n', text, re.I)
    return m.group(1).upper() if m else None


def _extract_cwpm(text: str) -> Optional[str]:
    """Format: Account Number 8-digit"""
    m = re.search(r'Account\s*Number\\n.*?Date\\n.*?Number\\n.*?\\n(\d{8})\\n', text, re.I)
    if m:
        return m.group(1)
    m = re.search(r'\\n(\d{8})\\n\d{2}/\d{2}/\d{2}', text)
    return m.group(1) if m else None


def _extract_pride_disposal(text: str) -> Optional[str]:
    """Format: ACCT. NO. or ACCT. #: followed by 8-digit"""
    # Header row format: ACCT. NO.\nACCOUNT NAME\n...\n01017092\n
    m = re.search(r'ACCT\.\s*NO\.\\nACCOUNT\s*NAME\\n.*?\\n(\d{8})\\n', text, re.I)
    if m:
        return m.group(1)
    # Direct format: ACCT. #:\n01017092\n
    m = re.search(r'ACCT\.\s*#:\\n(\d{8})\\n', text, re.I)
    return m.group(1) if m else None


def _extract_great_waste(text: str) -> Optional[str]:
    """Format: Account Number 7-digit"""
    m = re.search(r'Account\s*Number\\n.*?Date\\n(\d{7})\\n', text, re.I)
    if m:
        return m.group(1)
    m = re.search(r'Account\s*Number\\n(\d{7})\\n', text, re.I)
    return m.group(1) if m else None


def _extract_ontario_municipal(text: str) -> Optional[str]:
    """Format: Customer # - Account # NNNNNNN-NNNNNN"""
    m = re.search(r'Customer\s*#\s*-\s*Account\s*#\\n(\d{7})-(\d{6})\\n', text, re.I)
    if m:
        return m.group(1) + '-' + m.group(2)
    m = re.search(r'\\n(\d{7}-\d{6})\\n', text)
    return m.group(1) if m else None


def _extract_intermountain_disposal(text: str) -> Optional[str]:
    """Format: Account # at end of header row, text code (LOSCH, etc.) follows date
    Terms\\nDue Date\\nAccount #\\n...\\n7/30/2025\\nLOSCH\\n
    """
    m = re.search(r'Account\s*#\\n.*?\\n\d{1,2}/\d{1,2}/\d{4}\\n([A-Z]{3,10})\\n', text, re.I)
    if m:
        return m.group(1).upper()
    # Simpler pattern: date followed by text code
    m = re.search(r'\\n\d{1,2}/\d{1,2}/\d{4}\\n([A-Z]{4,10})\\n', text)
    return m.group(1).upper() if m else None


# NO_ACCOUNT batch 3
def _extract_river_parish(text: str) -> Optional[str]:
    """NO_ACCOUNT - Certificates of insurance, not invoices"""
    return None


# ============================================================
# VENDOR ADDITIONS DICTIONARY
# ============================================================

VENDOR_ADDITIONS = {
    # HIGH VOLUME - Verified patterns
    'Standard Waste': {
        'has_account': True,
        'format': 'XXX.XXXXXX (site code)',
        'examples': ['UPS.NJEDI1', 'UPS.NJSBR', 'UPS.NJNWK'],
        'extract': _extract_standard_waste,
        'notes': '~50% rate - many invoices are scale tickets without account IDs'
    },
    'All American Waste': {
        'has_account': True,
        'format': '6-digit',
        'examples': ['226822', '207498'],
        'extract': _extract_all_american_waste
    },
    'Pete & Pete': {
        'has_account': True,
        'format': '7-digit from scale tickets',
        'examples': ['3800044'],
        'extract': _extract_pete_pete
    },
    'Becker360': {
        'has_account': True,
        'format': 'Service Location code',
        'examples': ['UPS-MOAPP', 'UPS-KYBOW'],
        'extract': _extract_becker360
    },
    'Specific Waste': {
        'has_account': True,
        'format': 'Company ID (alpha+numeric)',
        'examples': ['aspec110854'],
        'extract': _extract_specific_waste,
        'notes': '~13% rate - limited coverage'
    },
    'Waste Path': {
        'has_account': True,
        'format': 'NNN-NNN',
        'examples': ['471-010', '471-002'],
        'extract': _extract_waste_path
    },
    'City of Boise': {
        'has_account': True,
        'format': '15-digit',
        'examples': ['955224300288241'],
        'extract': _extract_city_of_boise
    },
    'Wise Environmental': {
        'has_account': True,
        'format': '6-digit',
        'examples': ['651440'],
        'extract': _extract_wise_environmental
    },
    'Stryker Environmental': {
        'has_account': True,
        'format': 'UPS-Location',
        'examples': ['UPS-MEBANE', 'UPS-WINSTON'],
        'extract': _extract_stryker_environmental,
        'notes': '~37% rate'
    },
    'Las Vegas Recycling': {
        'has_account': True,
        'format': '8-digit Job Number',
        'examples': ['97223509'],
        'extract': _extract_las_vegas_recycling
    },
    'Redbox+': {
        'has_account': True,
        'format': 'XX-NNNN-NNNN',
        'examples': ['WA-2308-9398'],
        'extract': _extract_redbox_plus,
        'notes': 'Limited coverage - not all invoices have Account Id'
    },
    'Howard Disposal': {
        'has_account': True,
        'format': 'D-NNNN',
        'examples': ['D-6684'],
        'extract': _extract_howard_disposal
    },
    'CRI Curbside': {
        'has_account': False,
        'format': None,
        'examples': [],
        'extract': _extract_cri_curbside,
        'notes': 'Invoice-only vendor'
    },
    'Community Disposal': {
        'has_account': True,
        'format': 'CBRE-UPS-XXXXX',
        'examples': ['CBRE-UPS-FLJAC'],
        'extract': _extract_community_disposal
    },
    'Trash Taxi': {
        'has_account': True,
        'format': '12-digit TrashBilling ID',
        'examples': ['635530914203'],
        'extract': _extract_trash_taxi
    },
    'Grizzly Disposal': {
        'has_account': True,
        'format': '12-digit TrashBilling ID',
        'examples': ['120360126623', '120360126659'],
        'extract': _extract_grizzly_disposal
    },
    'Wompost': {
        'has_account': False,
        'format': None,
        'examples': [],
        'extract': _extract_wompost,
        'notes': 'Multiple document types, no consistent account'
    },

    # TRASHBILLING PLATFORM VENDORS
    'RDT Inc': {
        'has_account': True,
        'format': '12-digit TrashBilling ID',
        'examples': ['576220056746', '576220056811'],
        'extract': _extract_rdt_inc
    },
    'Dependable Sanitation': {
        'has_account': True,
        'format': '12-digit TrashBilling ID',
        'examples': ['105480106839', '105480106827'],
        'extract': _extract_dependable_sanitation
    },
    'Hill Country Waste': {
        'has_account': True,
        'format': '12-digit TrashBilling ID',
        'examples': ['641620313532', '641620313594'],
        'extract': _extract_hill_country_waste
    },
    'Hart Sanitation': {
        'has_account': True,
        'format': '12-digit TrashBilling ID',
        'examples': ['474810161791', '474810161804'],
        'extract': _extract_hart_sanitation
    },
    'Reliable Sanitation': {
        'has_account': True,
        'format': '12-digit TrashBilling ID',
        'examples': ['105500247824', '105500247812'],
        'extract': _extract_reliable_sanitation
    },
    'Thompson Sanitation': {
        'has_account': True,
        'format': '12-digit TrashBilling ID',
        'examples': ['562090511570', '562090377213'],
        'extract': _extract_thompson_sanitation,
        'notes': 'Partial coverage'
    },
    'Disposal Services LLC': {
        'has_account': True,
        'format': '12-digit TrashBilling ID',
        'examples': ['106540140974', '106540140936'],
        'extract': _extract_disposal_services_llc,
        'notes': 'Partial coverage'
    },

    # OTHER VENDORS WITH PATTERNS
    'E.J. Harrison & Sons': {
        'has_account': True,
        'format': 'N-NNNNNNNN',
        'examples': ['3-00320205'],
        'extract': _extract_ej_harrison,
        'notes': 'Partial coverage'
    },
    'First Piedmont': {
        'has_account': True,
        'format': '7-digit',
        'examples': ['1583411', '5038400'],
        'extract': _extract_first_piedmont,
        'notes': 'Partial coverage'
    },
    'Lawrence County Solid Waste': {
        'has_account': True,
        'format': '8-digit',
        'examples': ['00002420', '00000244'],
        'extract': _extract_lawrence_county,
        'notes': 'Partial coverage'
    },
    'Northern Waste': {
        'has_account': True,
        'format': '6-digit',
        'examples': ['002222'],
        'extract': _extract_northern_waste,
        'notes': 'Partial coverage'
    },
    'Green Guys': {
        'has_account': False,
        'format': None,
        'examples': [],
        'extract': _extract_green_guys,
        'notes': 'Payment receipts only - no customer account numbers'
    },

    # NO_ACCOUNT VENDORS
    'Boyas Recycling': {
        'has_account': False,
        'format': None,
        'examples': [],
        'extract': _extract_boyas_recycling,
        'notes': 'Uses PO numbers only'
    },
    'Rocky Ridge': {
        'has_account': False,
        'format': None,
        'examples': [],
        'extract': _extract_rocky_ridge,
        'notes': 'Invoice-only vendor'
    },
    'Heavenly Trash': {
        'has_account': False,
        'format': None,
        'examples': [],
        'extract': _extract_heavenly_trash,
        'notes': 'Invoice-only vendor'
    },
    'Conigliaro': {
        'has_account': False,
        'format': None,
        'examples': [],
        'extract': _extract_conigliaro,
        'notes': 'Uses work order numbers only'
    },
    'Premier Waste': {
        'has_account': False,
        'format': None,
        'examples': [],
        'extract': _extract_premier_waste,
        'notes': 'Invoice-only vendor'
    },

    # ============================================================
    # BATCH 2 VENDORS - January 2026 additional analysis
    # ============================================================

    # VENDORS WITH ACCOUNT PATTERNS
    'ACES Disposal': {
        'has_account': True,
        'format': 'NN-NNNNN-NNNNN (WM format)',
        'examples': ['17-97336-43007'],
        'extract': _extract_aces_disposal
    },
    'Solid Waste Authority': {
        'has_account': True,
        'format': '3-letter prefix + 6 digits',
        'examples': ['RSA001938'],
        'extract': _extract_solid_waste_authority
    },
    'Clean Slate': {
        'has_account': True,
        'format': '5-digit',
        'examples': ['42442', '10335'],
        'extract': _extract_clean_slate
    },
    'Corporate Services Consultants': {
        'has_account': True,
        'format': 'Letter + 6 digits',
        'examples': ['T022570'],
        'extract': _extract_corporate_services
    },
    'Bruin Waste Management': {
        'has_account': True,
        'format': '6-digit',
        'examples': ['790552', '275110'],
        'extract': _extract_bruin_waste
    },
    'Roosevelt UT': {
        'has_account': True,
        'format': 'NN-NNNN-NN',
        'examples': ['01-9691-00'],
        'extract': _extract_roosevelt_ut
    },
    'Texas Pride Disposal': {
        'has_account': True,
        'format': 'NN-NNNNN + digit',
        'examples': ['10-793926'],
        'extract': _extract_texas_pride
    },
    'City of Jackson': {
        'has_account': True,
        'format': '7-digit',
        'examples': ['7278319'],
        'extract': _extract_city_of_jackson
    },
    'AAA Disposal Service': {
        'has_account': True,
        'format': 'NN-NNNNNN',
        'examples': ['01-121001'],
        'extract': _extract_aaa_disposal
    },
    'Southern Sanitation': {
        'has_account': True,
        'format': '6-digit',
        'examples': ['210405'],
        'extract': _extract_southern_sanitation
    },

    # NO_ACCOUNT VENDORS - Batch 2
    'Walker Lake Disposal': {
        'has_account': False,
        'format': None,
        'examples': [],
        'extract': _extract_walker_lake,
        'notes': 'Simple customer numbers, not reliable'
    },
    'Curbside': {
        'has_account': False,
        'format': None,
        'examples': [],
        'extract': _extract_curbside,
        'notes': 'Uses work order numbers'
    },
    'Specialty Pallet': {
        'has_account': False,
        'format': None,
        'examples': [],
        'extract': _extract_specialty_pallet,
        'notes': 'Sales orders/BOL, uses PO numbers'
    },
    'Conex Recycling': {
        'has_account': False,
        'format': None,
        'examples': [],
        'extract': _extract_conex_recycling,
        'notes': 'Invoice-only vendor'
    },
    'Five Star Waste': {
        'has_account': False,
        'format': None,
        'examples': [],
        'extract': _extract_five_star_waste,
        'notes': 'Uses PO numbers only'
    },
    'Total Reclaim': {
        'has_account': False,
        'format': None,
        'examples': [],
        'extract': _extract_total_reclaim,
        'notes': 'Uses SO/Order numbers'
    },
    'Pennohio': {
        'has_account': False,
        'format': None,
        'examples': [],
        'extract': _extract_pennohio,
        'notes': 'Uses service location refs'
    },
    'Advance Machine & Hydraulic': {
        'has_account': False,
        'format': None,
        'examples': [],
        'extract': _extract_advance_machine,
        'notes': 'Equipment service invoices'
    },
    'D Crescio Trucking': {
        'has_account': False,
        'format': None,
        'examples': [],
        'extract': _extract_d_crescio,
        'notes': 'Text-based customer IDs'
    },
    'All Metals Recycling': {
        'has_account': False,
        'format': None,
        'examples': [],
        'extract': _extract_all_metals_recycling,
        'notes': 'Uses location codes'
    },
    'Southern Illinois Waste': {
        'has_account': False,
        'format': None,
        'examples': [],
        'extract': _extract_southern_illinois_waste,
        'notes': 'Uses location/PO numbers'
    },

    # ============================================================
    # BATCH 3 VENDORS - January 2026 additional analysis
    # ============================================================

    # VENDORS WITH ACCOUNT PATTERNS
    'Greif': {
        'has_account': True,
        'format': '9-digit supplier number',
        'examples': ['200048388'],
        'extract': _extract_greif
    },
    'Miami-Dade DSWM': {
        'has_account': True,
        'format': '7-digit (Great Waste format)',
        'examples': ['1129180'],
        'extract': _extract_miami_dade_dswm
    },
    'Pellitteri': {
        'has_account': True,
        'format': '8-digit',
        'examples': ['17966800'],
        'extract': _extract_pellitteri
    },
    'Penn Waste': {
        'has_account': True,
        'format': 'PC + 6 digits',
        'examples': ['PC174608'],
        'extract': _extract_penn_waste
    },
    'CWPM': {
        'has_account': True,
        'format': '8-digit',
        'examples': ['15147904'],
        'extract': _extract_cwpm
    },
    'PRIDE Disposal': {
        'has_account': True,
        'format': '8-digit',
        'examples': ['01017092'],
        'extract': _extract_pride_disposal
    },
    'Great Waste': {
        'has_account': True,
        'format': '7-digit',
        'examples': ['1129330'],
        'extract': _extract_great_waste
    },
    'Ontario Municipal': {
        'has_account': True,
        'format': 'NNNNNNN-NNNNNN',
        'examples': ['2268088-190941'],
        'extract': _extract_ontario_municipal
    },
    'Intermountain Disposal': {
        'has_account': True,
        'format': 'Text code (3-10 letters)',
        'examples': ['LOSCH'],
        'extract': _extract_intermountain_disposal
    },

    # NO_ACCOUNT - Batch 3
    'River Parish Disposal': {
        'has_account': False,
        'format': None,
        'examples': [],
        'extract': _extract_river_parish,
        'notes': 'Certificates of insurance, not invoices'
    },
}


def test_additions():
    """Test extraction functions with sample text"""
    import pandas as pd

    ocr = pd.read_csv('../../account_linkage/data/output/ocr_step3_invoices.csv', low_memory=False)

    print('Testing VENDOR_ADDITIONS extraction functions:\n')

    total_new_extractions = 0
    for vendor, config in VENDOR_ADDITIONS.items():
        if not config['has_account']:
            continue

        samples = ocr[ocr['detected_vendor'] == vendor]['raw_text'].head(30).tolist()
        if not samples:
            continue

        successes = 0
        examples = []
        for sample in samples:
            result = config['extract'](sample)
            if result:
                successes += 1
                if result not in examples:
                    examples.append(result)

        total_invoices = len(ocr[ocr['detected_vendor'] == vendor])
        rate = successes / len(samples) if samples else 0
        expected = int(total_invoices * rate)
        total_new_extractions += expected

        status = '✓' if rate >= 0.7 else ('~' if rate >= 0.4 else '✗')
        print(f'{status} {vendor}: {successes}/{len(samples)} ({rate:.0%}) [{total_invoices} inv] ~{expected} new')
        if examples:
            print(f'    Examples: {examples[:3]}')

    print(f'\nTotal expected new extractions: ~{total_new_extractions}')


if __name__ == '__main__':
    test_additions()
