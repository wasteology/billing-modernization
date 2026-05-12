#!/usr/bin/env python3
"""
Account Linkage Engine (v4 - Voucher-First with Improved Extraction)

Links hauler invoice account numbers to CIE trade service IDs using a
voucher-validated join approach that prioritizes the correct data flow.

CRITICAL: billing_reference is TRUNCATED on grouped billing. One truncated
billing_reference can map to 1000+ services across multiple vendors.

CORRECT FLOW (voucher-first):
  OCR ──fuzzy match──► Voucher ──► billing_reference ──► service_id
       (vendor+amount+date)    (ACTUAL invoice#)

WRONG FLOW (DO NOT USE):
  OCR.invoice_number ──► billing_reference ──► service_id   ❌ BROKEN

LINK TYPES (Trust Levels):
- VOUCHER_VALIDATED: HIGH trust - OCR matched voucher, voucher invoice# = billing_ref
- DIRECT_SINGLE_VENDOR: MEDIUM trust - invoice# exact match, billing_ref has ONE vendor
- SUBSTRING_SINGLE_VENDOR: MEDIUM trust - invoice# substring match, single vendor
- DIRECT_MULTI_VENDOR: LOW trust - invoice# exact match, but billing_ref has MULTIPLE vendors
- VOUCHER_ONLY: NONE - OCR matched voucher but couldn't link to service (recorded for future)

ACTIVE SERVICE FILTERING:
- Only matches ACTIVE services from Azure SQL
- Active = end_date IS NULL OR end_date >= today

Data Sources:
- OCR: Pre-extracted via parsing_engines (ocr_step3_invoices.csv + ocr_step2_accounts.csv)
- Billing Charges: CIE billing system export (requires service_id column)
- Voucher Export: Payment records for fuzzy matching (VoucherExport_*.csv) - REQUIRED
- Azure SQL: Services table for active service filtering
"""

import pandas as pd
import re
import time
from pathlib import Path
from typing import Optional, Dict, List, Set, Tuple
from collections import defaultdict
from datetime import datetime, timedelta
import glob
import sys
import struct
import logging

logger = logging.getLogger(__name__)


# =============================================================================
# Azure SQL Connection for Active Services
# =============================================================================

def get_active_services_from_azure(
    sql_server: str = "wasteology.database.windows.net",
    sql_database: str = "wasteology",
    sql_driver: str = "{ODBC Driver 18 for SQL Server}"
) -> Set[int]:
    """
    Query Azure SQL for active service_ids.

    Active services have:
    - is_active = 'Yes' in the services table

    Args:
        sql_server: Azure SQL server hostname
        sql_database: Database name
        sql_driver: ODBC driver string

    Returns:
        Set of active service_ids
    """
    try:
        import pyodbc
        from azure.identity import AzureCliCredential, DefaultAzureCredential
    except ImportError:
        logger.warning("pyodbc or azure-identity not installed. Skipping active service filter.")
        return set()

    logger.info("Connecting to Azure SQL for active services...")

    try:
        # Try Azure CLI first
        try:
            credential = AzureCliCredential()
            token = credential.get_token("https://database.windows.net/.default")
            logger.info("  Using Azure CLI credentials")
        except Exception:
            logger.info("  Azure CLI not available, using default credential chain")
            credential = DefaultAzureCredential()
            token = credential.get_token("https://database.windows.net/.default")

        # Convert token to bytes for ODBC
        token_bytes = token.token.encode("UTF-16-LE")
        token_struct = struct.pack(f'<I{len(token_bytes)}s', len(token_bytes), token_bytes)

        conn_str = (
            f"Driver={sql_driver};"
            f"Server={sql_server};"
            f"Database={sql_database};"
            f"Encrypt=yes;"
            f"TrustServerCertificate=no;"
        )

        SQL_COPT_SS_ACCESS_TOKEN = 1256
        conn = pyodbc.connect(
            conn_str,
            attrs_before={SQL_COPT_SS_ACCESS_TOKEN: token_struct}
        )

        query = """
        SELECT DISTINCT service_id
        FROM wasteology.new_ct.services
        WHERE is_active = 'Yes'
        """

        df = pd.read_sql(query, conn)
        conn.close()

        active_services = set(df['service_id'].astype(int))
        logger.info(f"  Found {len(active_services):,} active services")
        return active_services

    except Exception as e:
        logger.warning(f"Could not connect to Azure SQL: {e}")
        logger.warning("Proceeding without active service filter")
        return set()


def get_billing_charges_from_azure(
    lookback_days: int = 120,
    sql_server: str = "wasteology.database.windows.net",
    sql_database: str = "wasteology",
    sql_driver: str = "{ODBC Driver 18 for SQL Server}"
) -> Optional[pd.DataFrame]:
    """
    Query Azure SQL for billing charges with service_id.

    Args:
        lookback_days: Only include charges from the last N days (0 = no limit)
        sql_server: Azure SQL server hostname
        sql_database: Database name
        sql_driver: ODBC driver string

    Returns:
        DataFrame with billing_reference, service_id, vendor_name, transaction_date
        or None if connection fails
    """
    try:
        import pyodbc
        from azure.identity import AzureCliCredential, DefaultAzureCredential
    except ImportError:
        logger.error("pyodbc or azure-identity not installed. Cannot query billing charges.")
        return None

    print("Connecting to Azure SQL for billing charges...")

    try:
        # Try Azure CLI first
        try:
            credential = AzureCliCredential()
            token = credential.get_token("https://database.windows.net/.default")
            print("  Using Azure CLI credentials")
        except Exception:
            print("  Azure CLI not available, using default credential chain")
            credential = DefaultAzureCredential()
            token = credential.get_token("https://database.windows.net/.default")

        # Convert token to bytes for ODBC
        token_bytes = token.token.encode("UTF-16-LE")
        token_struct = struct.pack(f'<I{len(token_bytes)}s', len(token_bytes), token_bytes)

        conn_str = (
            f"Driver={sql_driver};"
            f"Server={sql_server};"
            f"Database={sql_database};"
            f"Encrypt=yes;"
            f"TrustServerCertificate=no;"
        )

        SQL_COPT_SS_ACCESS_TOKEN = 1256
        conn = pyodbc.connect(
            conn_str,
            attrs_before={SQL_COPT_SS_ACCESS_TOKEN: token_struct}
        )

        # Build query with optional date filter
        if lookback_days > 0:
            date_filter = f"AND transaction_date >= DATEADD(DAY, -{lookback_days}, GETDATE())"
        else:
            date_filter = ""

        query = f"""
        SELECT
            billing_reference,
            service_id,
            vendor_name,
            transaction_date
        FROM wasteology.new_ct.billing_charges
        WHERE billing_reference IS NOT NULL
          AND billing_reference != ''
          AND service_id IS NOT NULL
          AND service_id != 0
          {date_filter}
        """

        print(f"  Querying billing charges (lookback: {lookback_days} days)...")
        df = pd.read_sql(query, conn)
        conn.close()

        # Convert types
        df['service_id'] = df['service_id'].astype(str)
        df['billing_reference'] = df['billing_reference'].astype(str)
        df['vendor_name'] = df['vendor_name'].astype(str)

        print(f"  Retrieved {len(df):,} billing charge records")
        return df

    except Exception as e:
        logger.error(f"Could not query billing charges from Azure SQL: {e}")
        print(f"  ERROR: {e}")
        return None


# =============================================================================
# Amount and Date Extraction from Raw OCR Text
# =============================================================================

# =============================================================================
# Amount Due & Date Extraction — imported from parsing_engines (canonical source)
# =============================================================================
# Previously duplicated here with 40 amount patterns and 16 date patterns.
# Replaced with imports from parsing_engines to avoid drift and get access to
# 1,113+ vendor-specific date extractors and vendor-dispatch amount extraction.

sys.path.insert(0, '/home/scstclair/projects/parsing_engines')
from amount_due.amount_due_extraction_engine import extract_bill_total as _canonical_extract_bill_total
from dates.date_extraction_engine import extract_invoice_date as _canonical_extract_invoice_date


def extract_bill_total(raw_text: str) -> Optional[float]:
    """Extract bill total — delegates to parsing_engines canonical engine.

    Pandas-safe wrapper: handles NaN/None before calling canonical engine.
    """
    if not raw_text or pd.isna(raw_text):
        return None
    return _canonical_extract_bill_total(str(raw_text))


def extract_invoice_date(raw_text: str) -> Optional[str]:
    """Extract invoice date — delegates to parsing_engines canonical engine.

    Pandas-safe wrapper: handles NaN/None before calling canonical engine.
    Uses generic (non-vendor) signature since linkage doesn't have vendor context
    at the point where .apply() is called on raw_text.
    """
    if not raw_text or pd.isna(raw_text):
        return None
    return _canonical_extract_invoice_date(str(raw_text))


def extract_invoice_month(raw_text: str) -> Optional[str]:
    """
    Extract invoice month from raw OCR text.

    Args:
        raw_text: Raw OCR text from invoice

    Returns:
        Month in YYYY-MM format, or None if not found
    """
    date = extract_invoice_date(raw_text)
    if date:
        return date[:7]  # YYYY-MM
    return None


# =============================================================================
# Vendor Matching Utilities
# =============================================================================

# Equipment-only vendors that always pair with a primary hauler
EQUIPMENT_ONLY_VENDORS = {
    'smarttrash', 'waste vision', 'compology', 'enevo', 'bigbelly',
    'ecube labs', 'sensoneo', 'nordsense', 'allstate equipment'
}

# Known broker/reseller relationships (detected -> billing)
KNOWN_RELATIONSHIPS = {
    ('stericycle', 'shred-it'),
    ('shred-it', 'stericycle'),
}


def normalize_vendor_name(name: str) -> str:
    """Normalize vendor name for comparison."""
    if not name or pd.isna(name):
        return ''

    name = str(name).lower().strip()

    # Remove common suffixes
    for suffix in [', inc', ' inc', ', llc', ' llc', ', ltd', ' ltd',
                   ' corp', ' corporation', ' co', ' company', ' services',
                   ' service', ' disposal', ' waste', ' recycling', ' refuse',
                   ' sanitation', ' hauling', ' environmental']:
        name = name.replace(suffix, '')

    # Remove punctuation
    name = name.replace(',', '').replace('.', '').replace('-', ' ')
    name = name.replace("'", '').replace('"', '')

    # Collapse whitespace
    return ' '.join(name.split())


def vendors_match(detected: str, billing: str) -> bool:
    """
    Check if detected vendor and billing vendor refer to the same entity.

    Returns True if vendors match or have a known relationship.
    """
    v1 = normalize_vendor_name(detected)
    v2 = normalize_vendor_name(billing)

    if not v1 or not v2:
        return False

    # Exact match
    if v1 == v2:
        return True

    # Known relationships
    if (v1, v2) in KNOWN_RELATIONSHIPS:
        return True

    # First word match (unless ambiguous)
    v1_words = v1.split()
    v2_words = v2.split()

    ambiguous = {'best', 'all', 'american', 'city', 'national', 'united',
                 'first', 'green', 'clean', 'pro', 'a', 'the', 'new', 'big'}

    if v1_words and v2_words and v1_words[0] == v2_words[0]:
        if v1_words[0] not in ambiguous:
            return True
        elif len(v1_words) >= 2 and len(v2_words) >= 2 and v1_words[1] == v2_words[1]:
            return True

    # Substring match (longer contains shorter)
    if len(v1) > len(v2) * 1.5 and v2 in v1:
        return True
    if len(v2) > len(v1) * 1.5 and v1 in v2:
        return True

    return False


def is_equipment_only_vendor(vendor: str) -> bool:
    """Check if vendor is equipment-only (never primary hauler)."""
    normalized = normalize_vendor_name(vendor)
    return any(eq in normalized for eq in EQUIPMENT_ONLY_VENDORS)


# =============================================================================
# Billing Reference Trust Analysis
# =============================================================================

def compute_billing_ref_trust(billing_df: pd.DataFrame) -> Tuple[Set[str], Set[str]]:
    """
    Pre-compute which billing_references are trustworthy.

    Trustworthy = billing_reference maps to ONLY ONE vendor
    Untrustworthy = billing_reference maps to MULTIPLE vendors (grouped billing)

    Args:
        billing_df: DataFrame with billing_reference and vendor_name columns

    Returns:
        Tuple of (trustworthy_refs set, untrustworthy_refs set)
    """
    logger.info("Computing billing reference trust levels...")

    # Count unique vendors per billing_reference
    ref_vendor_counts = billing_df.groupby('billing_reference')['vendor_name'].nunique()

    trustworthy_refs = set(ref_vendor_counts[ref_vendor_counts == 1].index)
    untrustworthy_refs = set(ref_vendor_counts[ref_vendor_counts > 1].index)

    total = len(trustworthy_refs) + len(untrustworthy_refs)
    trust_pct = 100 * len(trustworthy_refs) / total if total > 0 else 0

    logger.info(f"  Trustworthy (single vendor): {len(trustworthy_refs):,} ({trust_pct:.1f}%)")
    logger.info(f"  Untrustworthy (multi vendor): {len(untrustworthy_refs):,} ({100-trust_pct:.1f}%)")

    return trustworthy_refs, untrustworthy_refs


# =============================================================================
# Voucher Fuzzy Matching
# =============================================================================

def load_voucher_data(voucher_dir: str) -> pd.DataFrame:
    """
    Load and combine all voucher export files.

    Args:
        voucher_dir: Directory containing VoucherExport_*.csv files

    Returns:
        Combined DataFrame with standardized columns
    """
    voucher_files = glob.glob(str(Path(voucher_dir) / 'VoucherExport_*.csv'))

    if not voucher_files:
        logger.warning(f"No voucher files found in {voucher_dir}")
        return pd.DataFrame()

    dfs = []
    for f in voucher_files:
        try:
            df = pd.read_csv(f, dtype=str)
            dfs.append(df)
        except Exception as e:
            logger.warning(f"Could not load {f}: {e}")

    if not dfs:
        return pd.DataFrame()

    combined = pd.concat(dfs, ignore_index=True)

    # Standardize column names (from VoucherExport format)
    col_map = {
        'Vendor Name': 'vendor',
        'Invoice Date': 'invoice_date',
        'Invoice No': 'invoice_no',
        'Payment Amount': 'payment_amount'
    }

    for old, new in col_map.items():
        if old in combined.columns:
            combined = combined.rename(columns={old: new})

    logger.info(f"Loaded {len(combined):,} voucher records from {len(voucher_files)} files")
    return combined


def parse_voucher_date(date_str: str) -> Optional[str]:
    """Parse voucher date to YYYY-MM format."""
    if not date_str or pd.isna(date_str):
        return None

    date_str = str(date_str).strip()

    for fmt in ['%Y.%m.%d', '%Y-%m-%d', '%Y/%m/%d', '%m/%d/%Y',
                '%m-%d-%Y', '%Y-%m-%d %H:%M:%S']:
        try:
            dt = datetime.strptime(date_str.split()[0], fmt)
            return dt.strftime('%Y-%m')
        except ValueError:
            continue
    return None


def parse_voucher_amount(amount_str: str) -> Optional[float]:
    """Parse voucher payment amount to float."""
    if not amount_str or pd.isna(amount_str):
        return None

    try:
        cleaned = str(amount_str).replace('$', '').replace(',', '').strip()
        return float(cleaned)
    except ValueError:
        return None


def build_voucher_index(voucher_df: pd.DataFrame) -> Dict[str, List[Dict]]:
    """
    Build voucher index for fuzzy matching.

    Index by normalized vendor name for fast lookup.

    Args:
        voucher_df: DataFrame with vendor, invoice_date, invoice_no, payment_amount

    Returns:
        Dict mapping normalized vendor -> list of voucher records
    """
    index = defaultdict(list)

    for _, row in voucher_df.iterrows():
        vendor = normalize_vendor_name(row.get('vendor', ''))
        invoice_no = str(row.get('invoice_no', '')).strip().upper()
        amount = parse_voucher_amount(row.get('payment_amount'))
        month = parse_voucher_date(row.get('invoice_date'))

        if vendor and invoice_no and invoice_no != 'NAN':
            index[vendor].append({
                'invoice_no': invoice_no,
                'amount': amount,
                'month': month,
                'vendor_raw': row.get('vendor', '')
            })

    return index


def compute_amount_tolerance(amount: float) -> float:
    """
    Compute amount tolerance based on invoice amount.

    - For amounts > $100: ±$1.00 (handles rounding/fees)
    - For amounts <= $100: ±10% (percentage-based for small invoices)

    This prevents false positives on common amounts like $0.00, $100.00
    while still allowing reasonable tolerance for legitimate matches.

    Args:
        amount: Invoice amount

    Returns:
        Tolerance value in dollars
    """
    if amount > 100:
        return 1.00  # Fixed $1.00 tolerance for larger amounts
    else:
        return max(0.01, amount * 0.10)  # 10% tolerance, minimum $0.01


def fuzzy_match_voucher(
    ocr_vendor: str,
    ocr_amount: Optional[float],
    ocr_month: Optional[str],
    voucher_index: Dict[str, List[Dict]],
    require_month_match: bool = True,
    require_vendor_match: bool = True
) -> Optional[Dict]:
    """
    Fuzzy match OCR record to voucher using vendor + amount + date.

    TIGHTENED MATCHING CRITERIA (v4):
    1. Vendor name MUST match (normalized, exact) - prevents cross-vendor false positives
    2. Payment amount matches with smart tolerance:
       - >$100: ±$1.00 (handles rounding/fees)
       - ≤$100: ±10% (percentage-based for small invoices)
    3. Invoice month MUST match (same YYYY-MM) - prevents cross-period false positives

    These tight criteria are necessary because:
    - Duplicate amounts: $0.00 appears 188 times/month, $100.00 appears 63 times
    - Date batching: 95% of vouchers posted on 1st of month
    - Loose matching creates high false positive rate

    Args:
        ocr_vendor: Detected vendor from OCR
        ocr_amount: Bill total extracted from OCR
        ocr_month: Invoice month extracted from OCR (YYYY-MM)
        voucher_index: Pre-built voucher index
        require_month_match: If True, reject if months don't match (default True)
        require_vendor_match: If True, require exact vendor match (default True)

    Returns:
        Matching voucher record with confidence score, or None
    """
    if not ocr_vendor or not ocr_amount:
        return None

    normalized_vendor = normalize_vendor_name(ocr_vendor)

    if not normalized_vendor:
        return None

    # Compute smart amount tolerance
    tolerance = compute_amount_tolerance(ocr_amount)

    # Get candidates from vendor index
    if require_vendor_match:
        # Exact vendor match only (O(1) lookup)
        candidates = voucher_index.get(normalized_vendor, [])
    else:
        # Fall back to all candidates (slower, higher false positive rate)
        candidates = []
        for vendor_candidates in voucher_index.values():
            candidates.extend(vendor_candidates)

    best_match = None
    best_score = 0

    for voucher in candidates:
        voucher_amount = voucher.get('amount')
        voucher_month = voucher.get('month')

        # Skip if no amount in voucher
        if voucher_amount is None:
            continue

        # Amount match with smart tolerance
        amount_diff = abs(ocr_amount - voucher_amount)
        if amount_diff > tolerance:
            continue

        # Month match (required by default)
        if require_month_match:
            if not ocr_month or not voucher_month:
                continue  # Can't verify month match
            if ocr_month != voucher_month:
                continue

        # Compute confidence score
        # Higher score = better match
        score = 100

        # Exact amount match is best
        if amount_diff < 0.01:
            score += 50
        elif amount_diff < 0.50:
            score += 25

        # Month match bonus
        if ocr_month and voucher_month and ocr_month == voucher_month:
            score += 25

        if score > best_score:
            best_score = score
            best_match = voucher.copy()
            best_match['match_score'] = score

    return best_match


# =============================================================================
# AccountLinker Class
# =============================================================================

class AccountLinker:
    """
    Account -> Service ID linker using precomputed lookup table.

    Supports temporal validity windows and link_type based trust levels.

    Usage:
        linker = AccountLinker()
        linker.load_lookup('path/to/account_service_lookup.csv')

        # Get service_id for an account
        service_id = linker.get_service_id(vendor='Waste Management', account='12345678')

        # Get link type info
        info = linker.get_link_info(vendor='Waste Management', account='12345678')
        print(info['link_type'])  # DIRECT_SINGLE_VENDOR
    """

    def __init__(self):
        self.lookup: Dict[Tuple[str, str], Set[int]] = {}  # (vendor, account) -> {service_ids}
        self.reverse_lookup: Dict[int, Set[Tuple[str, str]]] = {}  # service_id -> {(vendor, account)}
        self.link_info: Dict[Tuple[str, str, int], Dict] = {}  # (vendor, account, service_id) -> info
        self._loaded = False

    def load_lookup(self, path: str) -> None:
        """Load precomputed lookup table with link_type column."""
        df = pd.read_csv(path, dtype={'service_id': int})

        for _, row in df.iterrows():
            vendor = str(row.get('detected_vendor', '')).strip()
            account = str(row.get('account_number', '')).strip()
            service_id = int(row['service_id'])

            if vendor and account:
                key = (vendor.lower(), account)
                if key not in self.lookup:
                    self.lookup[key] = set()
                self.lookup[key].add(service_id)

                if service_id not in self.reverse_lookup:
                    self.reverse_lookup[service_id] = set()
                self.reverse_lookup[service_id].add((vendor, account))

                # Store link type and other info
                info_key = (vendor.lower(), account, service_id)
                self.link_info[info_key] = {
                    'link_type': str(row.get('link_type', '')).strip() if pd.notna(row.get('link_type')) else '',
                    'billing_vendor': str(row.get('billing_vendor', '')).strip() if pd.notna(row.get('billing_vendor')) else '',
                    'invoice_number': str(row.get('invoice_number', '')).strip() if pd.notna(row.get('invoice_number')) else ''
                }

        self._loaded = True

    def get_service_id(self, vendor: str, account: str) -> Optional[int]:
        """
        Get service_id for a vendor/account pair.

        Prefers HIGH trust linkages over LOW trust.
        """
        if not self._loaded:
            raise RuntimeError("Lookup not loaded. Call load_lookup() first.")

        key = (vendor.lower(), account)
        service_ids = self.lookup.get(key, set())

        if not service_ids:
            return None

        # Sort by trust level (HIGHEST first)
        # VOUCHER_VALIDATED is now highest trust since it uses the correct data flow
        trust_order = {'VOUCHER_VALIDATED': 1, 'DIRECT_SINGLE_VENDOR': 2,
                       'SUBSTRING_SINGLE_VENDOR': 3, 'DIRECT_MULTI_VENDOR': 4}

        best_sid = None
        best_trust = 999

        for sid in service_ids:
            info_key = (vendor.lower(), account, sid)
            info = self.link_info.get(info_key, {})
            link_type = info.get('link_type', '')
            trust = trust_order.get(link_type, 5)

            if trust < best_trust:
                best_trust = trust
                best_sid = sid

        return best_sid if best_sid else next(iter(service_ids))

    def get_all_service_ids(self, vendor: str, account: str) -> Set[int]:
        """Get all service_ids for a vendor/account pair."""
        if not self._loaded:
            raise RuntimeError("Lookup not loaded. Call load_lookup() first.")

        key = (vendor.lower(), account)
        return self.lookup.get(key, set())

    def get_link_info(self, vendor: str, account: str, service_id: int = None) -> Optional[Dict]:
        """
        Get link information for a vendor/account/service combination.

        Returns dict with:
            link_type: DIRECT_SINGLE_VENDOR, VOUCHER_VALIDATED, etc.
            billing_vendor: Vendor name from billing system
            invoice_number: Invoice number used for linkage
        """
        if not self._loaded:
            raise RuntimeError("Lookup not loaded. Call load_lookup() first.")

        if service_id is None:
            service_id = self.get_service_id(vendor, account)
            if service_id is None:
                return None

        info_key = (vendor.lower(), account, service_id)
        return self.link_info.get(info_key)

    def get_accounts_for_service(self, service_id: int) -> List[Tuple[str, str]]:
        """Get all (vendor, account) pairs linked to a service_id."""
        if not self._loaded:
            raise RuntimeError("Lookup not loaded. Call load_lookup() first.")

        return list(self.reverse_lookup.get(service_id, set()))

    def stats(self) -> Dict[str, int]:
        """Return lookup statistics including link type breakdown."""
        link_type_counts = defaultdict(int)

        for info in self.link_info.values():
            lt = info.get('link_type', 'UNKNOWN')
            link_type_counts[lt] += 1

        return {
            'unique_vendor_account_pairs': len(self.lookup),
            'unique_service_ids': len(self.reverse_lookup),
            'total_mappings': sum(len(s) for s in self.lookup.values()),
            'direct_single_vendor': link_type_counts.get('DIRECT_SINGLE_VENDOR', 0),
            'voucher_validated': link_type_counts.get('VOUCHER_VALIDATED', 0),
            'substring_single_vendor': link_type_counts.get('SUBSTRING_SINGLE_VENDOR', 0),
            'direct_multi_vendor': link_type_counts.get('DIRECT_MULTI_VENDOR', 0),
            'voucher_only': link_type_counts.get('VOUCHER_ONLY', 0)
        }


# =============================================================================
# Linkage Pipeline
# =============================================================================

def run_linkage_pipeline(
    ocr_path: str,
    output_path: str,
    billing_path: str = None,
    use_azure_billing: bool = False,
    voucher_dir: str = None,
    use_substring_matching: bool = True,
    ocr_accounts_path: str = None,
    filter_active_services: bool = True,
    sql_server: str = "wasteology.database.windows.net",
    sql_database: str = "wasteology",
    lookback_days: int = 120,
    phase_delay: float = 2.0
) -> Dict[str, int]:
    """
    Run the trust-based linkage pipeline.

    Uses pre-extracted data from parsing_engines, classifies linkages by
    trust level (link_type), and optionally filters to active services only.

    Args:
        ocr_path: Path to OCR CSV with invoice_number (ocr_step3_invoices.csv)
        output_path: Path to save the lookup CSV
        billing_path: Path to billing charges CSV (required if use_azure_billing=False)
        use_azure_billing: If True, query billing charges from Azure SQL instead of CSV
        voucher_dir: Optional directory with VoucherExport_*.csv for fuzzy matching
        use_substring_matching: Enable substring matching for invoice numbers
        ocr_accounts_path: Optional path to OCR accounts CSV (ocr_step2_accounts.csv)
        filter_active_services: If True, only link to active services (requires Azure SQL)
        sql_server: Azure SQL server for active service lookup
        sql_database: Azure SQL database name
        lookback_days: Only include billing charges from the last N days (default 120)
        phase_delay: Seconds to pause between phases to prevent connection overload (default 2.0)

    Returns:
        Dict with pipeline statistics
    """
    stats = {
        'ocr_invoices': 0,
        'ocr_with_invoice_number': 0,
        'billing_references': 0,
        'active_services': 0,
        'direct_single_vendor': 0,
        'direct_multi_vendor': 0,
        'substring_single_vendor': 0,
        'voucher_validated': 0,
        'voucher_only': 0,
        'unique_mappings': 0,
        'trustworthy_refs': 0,
        'untrustworthy_refs': 0
    }

    # ==========================================================================
    # PHASE 0: Get active services from Azure SQL (optional)
    # ==========================================================================
    active_services = set()
    if filter_active_services:
        print("Phase 0: Fetching active services from Azure SQL...")
        active_services = get_active_services_from_azure(sql_server, sql_database)
        stats['active_services'] = len(active_services)

        if not active_services:
            print("  WARNING: Could not fetch active services. Proceeding without filter.")

    # ==========================================================================
    # PHASE 1: Load pre-extracted OCR data
    # ==========================================================================
    print("\nPhase 1: Loading pre-extracted OCR data...")
    print("  IMPORTANT: Using pre-extracted fields only (no raw OCR text for invoice matching)")

    ocr_df = pd.read_csv(ocr_path, dtype=str)
    stats['ocr_invoices'] = len(ocr_df)

    # If separate accounts file provided, merge by md5_hash
    if ocr_accounts_path:
        print(f"  Merging with accounts from {ocr_accounts_path}")
        accounts_df = pd.read_csv(ocr_accounts_path, dtype=str)
        accounts_df = accounts_df[['md5_hash', 'account_number']].drop_duplicates(subset=['md5_hash'])
        ocr_df = ocr_df.merge(accounts_df, on='md5_hash', how='left')
        print(f"  Merged: {len(ocr_df):,} records")

    # Filter to rows with invoice numbers and account numbers
    ocr_df = ocr_df[ocr_df['invoice_number'].notna() & (ocr_df['invoice_number'] != '')]

    if 'account_number' in ocr_df.columns:
        ocr_df = ocr_df[ocr_df['account_number'].notna() & (ocr_df['account_number'] != '')]
    else:
        print("  WARNING: No account_number column found. Linkages will lack account info.")

    stats['ocr_with_invoice_number'] = len(ocr_df)

    # Extract bill_total and invoice_date from raw_text (for voucher matching)
    if 'raw_text' in ocr_df.columns:
        print("  Extracting bill_total and invoice_date from raw_text...")
        ocr_df['bill_total'] = ocr_df['raw_text'].apply(extract_bill_total)
        ocr_df['invoice_month'] = ocr_df['raw_text'].apply(extract_invoice_month)

        with_amount = ocr_df['bill_total'].notna().sum()
        with_date = ocr_df['invoice_month'].notna().sum()
        print(f"    Extracted bill_total: {with_amount:,} ({100*with_amount/len(ocr_df):.1f}%)")
        print(f"    Extracted invoice_month: {with_date:,} ({100*with_date/len(ocr_df):.1f}%)")

    print(f"  {stats['ocr_invoices']:,} total OCR records")
    print(f"  {stats['ocr_with_invoice_number']:,} with extracted invoice numbers and accounts")

    # Build invoice number index: invoice_number -> [(ocr_record)]
    invoice_index = defaultdict(list)
    for _, row in ocr_df.iterrows():
        inv_num = str(row['invoice_number']).strip().upper()
        invoice_index[inv_num].append({
            'md5': row.get('md5_hash', ''),
            'detected_vendor': str(row.get('detected_vendor', '')).strip(),
            'account_number': str(row.get('account_number', '')).strip(),
            'bill_total': row.get('bill_total'),
            'invoice_month': row.get('invoice_month')
        })

    print(f"  {len(invoice_index):,} unique invoice numbers indexed")

    # ==========================================================================
    # PHASE 2: Load billing charges (from Azure SQL or CSV)
    # ==========================================================================
    if phase_delay > 0:
        print(f"\n  [Throttle] Pausing {phase_delay}s before Phase 2...")
        time.sleep(phase_delay)

    print("\nPhase 2: Loading billing charges...")

    if use_azure_billing:
        # Query billing charges from Azure SQL
        billing_df = get_billing_charges_from_azure(
            lookback_days=lookback_days,
            sql_server=sql_server,
            sql_database=sql_database
        )
        if billing_df is None:
            raise RuntimeError("Failed to query billing charges from Azure SQL. Check connection and credentials.")
        total_billing = len(billing_df)
        print(f"  Loaded {total_billing:,} billing records from Azure SQL")
    else:
        # Load from CSV file
        if not billing_path:
            raise ValueError("billing_path is required when use_azure_billing=False")

        billing_df = pd.read_csv(billing_path, dtype=str)
        total_billing = len(billing_df)

        # Ensure required columns
        required_cols = ['billing_reference', 'service_id', 'vendor_name']
        missing = [c for c in required_cols if c not in billing_df.columns]
        if missing:
            raise ValueError(f"Billing file missing required columns: {missing}")

        # Filter valid rows
        billing_df = billing_df[billing_df['billing_reference'].notna()]
        billing_df = billing_df[billing_df['service_id'].notna()]
        billing_df = billing_df[~billing_df['service_id'].isin(['0', '', 'nan'])]

        # Apply lookback filter on transaction_date
        if lookback_days > 0 and 'transaction_date' in billing_df.columns:
            cutoff_date = datetime.now() - timedelta(days=lookback_days)
            cutoff_str = cutoff_date.strftime('%Y-%m-%d')

            before_lookback = len(billing_df)
            billing_df['_parsed_date'] = pd.to_datetime(billing_df['transaction_date'], errors='coerce')
            billing_df = billing_df[billing_df['_parsed_date'] >= cutoff_date]
            billing_df = billing_df.drop(columns=['_parsed_date'])

            print(f"  Lookback filter ({lookback_days} days, >= {cutoff_str}): {before_lookback:,} -> {len(billing_df):,} records")
        elif lookback_days > 0:
            print(f"  WARNING: No transaction_date column found - skipping lookback filter")

    # Normalize billing_reference to uppercase
    billing_df['billing_reference'] = billing_df['billing_reference'].str.strip().str.upper()

    # Filter to active services only
    if active_services:
        before = len(billing_df)
        billing_df['service_id_int'] = pd.to_numeric(billing_df['service_id'], errors='coerce')
        billing_df = billing_df[billing_df['service_id_int'].isin(active_services)]
        after = len(billing_df)
        print(f"  Filtered to active services: {before:,} -> {after:,} records")

    print(f"  {len(billing_df):,} billing records (from {total_billing:,} total, after filters)")

    # ==========================================================================
    # PHASE 2.5: Compute billing reference trust levels
    # ==========================================================================
    print("\nPhase 2.5: Computing billing reference trust levels...")
    trustworthy_refs, untrustworthy_refs = compute_billing_ref_trust(billing_df)
    stats['trustworthy_refs'] = len(trustworthy_refs)
    stats['untrustworthy_refs'] = len(untrustworthy_refs)

    # Build billing index: billing_reference -> [{service_id, vendor_name, ...}]
    billing_index = defaultdict(list)
    for _, row in billing_df.iterrows():
        ref = str(row['billing_reference']).strip().upper()
        if ref and ref != 'NAN':
            billing_index[ref].append({
                'service_id': str(row['service_id']).strip(),
                'vendor_name': str(row.get('vendor_name', '')).strip(),
                'transaction_date': str(row.get('transaction_date', '')).strip()
            })

    stats['billing_references'] = len(billing_index)
    print(f"  {stats['billing_references']:,} unique billing references")

    # ==========================================================================
    # PHASE 3: Load voucher data (optional)
    # ==========================================================================
    if phase_delay > 0:
        print(f"\n  [Throttle] Pausing {phase_delay}s before Phase 3...")
        time.sleep(phase_delay)

    voucher_index = {}
    voucher_invoice_set = set()

    if voucher_dir:
        print("\nPhase 3: Loading voucher data...")
        voucher_df = load_voucher_data(voucher_dir)

        if len(voucher_df) > 0:
            voucher_index = build_voucher_index(voucher_df)

            # Also build set of voucher invoice numbers
            for _, row in voucher_df.iterrows():
                inv_no = str(row.get('invoice_no', '')).strip().upper()
                if inv_no and inv_no != 'NAN':
                    voucher_invoice_set.add(inv_no)

            print(f"  {len(voucher_index):,} vendors indexed")
            print(f"  {len(voucher_invoice_set):,} unique invoice numbers")

    # ==========================================================================
    # PHASE 4: Voucher-validated matching (PRIMARY - use voucher as source of truth)
    # ==========================================================================
    # CRITICAL: This is now the PRIMARY matching path because:
    # - billing_reference is TRUNCATED on grouped billing
    # - Voucher has the ACTUAL un-truncated invoice number
    # - Going direct OCR → billing_reference creates garbage data
    # ==========================================================================
    if phase_delay > 0:
        print(f"\n  [Throttle] Pausing {phase_delay}s before Phase 4...")
        time.sleep(phase_delay)

    results = []
    matched_invoices = set()

    if voucher_dir and voucher_index:
        print("\nPhase 4: Voucher-validated matching (PRIMARY)...")
        print("  Using CORRECT flow: OCR → Voucher → billing_reference → service_id")

        voucher_matches = 0
        voucher_only_count = 0
        ocr_with_extraction = 0

        for inv_num, ocr_records in invoice_index.items():
            for ocr_rec in ocr_records:
                # Check if we have extracted amount and month for fuzzy matching
                has_amount = ocr_rec.get('bill_total') is not None
                has_month = ocr_rec.get('invoice_month') is not None

                if has_amount:
                    ocr_with_extraction += 1

                # Try voucher fuzzy match (TIGHT criteria)
                voucher_match = fuzzy_match_voucher(
                    ocr_vendor=ocr_rec['detected_vendor'],
                    ocr_amount=ocr_rec.get('bill_total'),
                    ocr_month=ocr_rec.get('invoice_month'),
                    voucher_index=voucher_index,
                    require_month_match=True,
                    require_vendor_match=True
                )

                if voucher_match:
                    # Use voucher's invoice number to find billing
                    voucher_inv = voucher_match['invoice_no']

                    if voucher_inv in billing_index:
                        # Found linkage via voucher - HIGH trust
                        matched_invoices.add(inv_num)
                        voucher_matches += 1

                        for billing_rec in billing_index[voucher_inv]:
                            # Additional validation: vendor should match
                            detected = ocr_rec['detected_vendor']
                            billing_vendor = billing_rec['vendor_name']
                            vendor_matches = vendors_match(detected, billing_vendor)

                            results.append({
                                'detected_vendor': detected,
                                'account_number': ocr_rec['account_number'],
                                'service_id': billing_rec['service_id'],
                                'billing_vendor': billing_vendor,
                                'invoice_number': voucher_inv,  # Use voucher's invoice#
                                'link_type': 'VOUCHER_VALIDATED',
                                'match_score': voucher_match.get('match_score', 0)
                            })
                            stats['voucher_validated'] += 1
                    else:
                        # Voucher matched but no billing record - record for future
                        voucher_only_count += 1

        stats['voucher_only'] = voucher_only_count
        stats['ocr_with_extraction'] = ocr_with_extraction

        print(f"  OCR with extracted amount: {ocr_with_extraction:,} ({100*ocr_with_extraction/len(invoice_index):.1f}%)")
        print(f"  Voucher-validated matches: {voucher_matches:,}")
        print(f"  Voucher-only (no billing): {voucher_only_count:,}")
    else:
        print("\nPhase 4: Voucher-validated matching SKIPPED")
        print("  WARNING: No voucher data provided (--voucher-dir)")
        print("  WARNING: Direct matching without voucher validation has HIGH false positive rate")
        print("  WARNING: Recommend providing voucher data for reliable linkages")

    # ==========================================================================
    # PHASE 5: Direct matching (FALLBACK - use only when voucher path fails)
    # ==========================================================================
    # NOTE: This path is LESS RELIABLE than voucher validation because:
    # - billing_reference may be truncated on grouped billing
    # - One truncated ref can match 1000+ unrelated services
    # ==========================================================================
    if phase_delay > 0:
        print(f"\n  [Throttle] Pausing {phase_delay}s before Phase 5...")
        time.sleep(phase_delay)

    print("\nPhase 5: Direct invoice number matching (FALLBACK)...")

    unmatched_invoices = set(invoice_index.keys()) - matched_invoices
    direct_matches = 0

    for inv_num in unmatched_invoices:
        if inv_num in billing_index:
            matched_invoices.add(inv_num)
            direct_matches += 1
            is_trustworthy = inv_num in trustworthy_refs

            for ocr_rec in invoice_index[inv_num]:
                for billing_rec in billing_index[inv_num]:
                    detected = ocr_rec['detected_vendor']
                    billing_vendor = billing_rec['vendor_name']
                    vendor_matches = vendors_match(detected, billing_vendor)

                    # Determine link_type based on trust
                    # Note: Direct matches are now MEDIUM trust, not HIGH
                    if is_trustworthy and vendor_matches:
                        link_type = 'DIRECT_SINGLE_VENDOR'
                        stats['direct_single_vendor'] += 1
                    elif is_trustworthy and not vendor_matches:
                        # Single vendor ref but vendor mismatch - could be name variation
                        link_type = 'DIRECT_SINGLE_VENDOR'
                        stats['direct_single_vendor'] += 1
                    elif not is_trustworthy and vendor_matches:
                        # Multi-vendor ref but vendors match - low trust
                        link_type = 'DIRECT_MULTI_VENDOR'
                        stats['direct_multi_vendor'] += 1
                    else:
                        # Multi-vendor ref AND vendor mismatch - very low trust
                        link_type = 'DIRECT_MULTI_VENDOR'
                        stats['direct_multi_vendor'] += 1

                    results.append({
                        'detected_vendor': detected,
                        'account_number': ocr_rec['account_number'],
                        'service_id': billing_rec['service_id'],
                        'billing_vendor': billing_vendor,
                        'invoice_number': inv_num,
                        'link_type': link_type
                    })

    print(f"  Direct matches (from {len(unmatched_invoices):,} unmatched): {direct_matches:,}")
    print(f"    DIRECT_SINGLE_VENDOR: {stats['direct_single_vendor']:,}")
    print(f"    DIRECT_MULTI_VENDOR: {stats['direct_multi_vendor']:,}")

    # ==========================================================================
    # PHASE 6: Substring matching (strict criteria to avoid false positives)
    # ==========================================================================
    # NOTE: Substring matching has HIGH false positive risk for short invoice numbers.
    # A 5-6 digit number like "13733" can easily appear as substring in unrelated refs.
    # Require EITHER:
    #   - Invoice number >= 8 characters (unlikely to be coincidental match)
    #   - OR vendor names match (validates the relationship)
    # ==========================================================================
    if use_substring_matching:
        if phase_delay > 0:
            print(f"\n  [Throttle] Pausing {phase_delay}s before Phase 6...")
            time.sleep(phase_delay)

        print("\nPhase 6: Substring matching (strict criteria)...")

        unmatched_invoices = set(invoice_index.keys()) - matched_invoices
        substring_matches = 0
        substring_skipped_short = 0

        # Only use trustworthy refs for substring matching
        trustworthy_billing_refs = list(trustworthy_refs & set(billing_index.keys()))

        for inv_num in unmatched_invoices:
            # Minimum 5 chars to even consider
            if len(inv_num) < 5:
                continue

            for ref in trustworthy_billing_refs:
                # Invoice number contained in billing reference
                if len(ref) > len(inv_num) and inv_num in ref:
                    # Get OCR records for this invoice
                    ocr_records = invoice_index[inv_num]
                    billing_records = billing_index[ref]

                    # For short invoice numbers (< 8 chars), REQUIRE vendor match
                    # to avoid false positives from coincidental substring matches
                    if len(inv_num) < 8:
                        # Check if ANY vendor combination matches
                        has_vendor_match = False
                        for ocr_rec in ocr_records:
                            for billing_rec in billing_records:
                                if vendors_match(ocr_rec['detected_vendor'], billing_rec['vendor_name']):
                                    has_vendor_match = True
                                    break
                            if has_vendor_match:
                                break

                        if not has_vendor_match:
                            substring_skipped_short += 1
                            continue  # Skip this match - likely false positive

                    # Valid match - record it
                    matched_invoices.add(inv_num)
                    substring_matches += 1

                    for ocr_rec in ocr_records:
                        for billing_rec in billing_records:
                            results.append({
                                'detected_vendor': ocr_rec['detected_vendor'],
                                'account_number': ocr_rec['account_number'],
                                'service_id': billing_rec['service_id'],
                                'billing_vendor': billing_rec['vendor_name'],
                                'invoice_number': inv_num,
                                'link_type': 'SUBSTRING_SINGLE_VENDOR'
                            })
                            stats['substring_single_vendor'] += 1
                    break  # Found match, move to next invoice

        print(f"  Substring matches: {substring_matches:,}")
        print(f"  Skipped (short inv#, no vendor match): {substring_skipped_short:,}")

    # ==========================================================================
    # PHASE 7: Save results
    # ==========================================================================
    print("\nPhase 7: Saving results...")

    if results:
        results_df = pd.DataFrame(results)

        # Deduplicate by account_number + service_id (keep highest trust link_type)
        # VOUCHER_VALIDATED is now #1 trust since it uses the correct data flow
        trust_order = {'VOUCHER_VALIDATED': 1, 'DIRECT_SINGLE_VENDOR': 2,
                       'SUBSTRING_SINGLE_VENDOR': 3, 'DIRECT_MULTI_VENDOR': 4}
        results_df['_trust_sort'] = results_df['link_type'].map(trust_order).fillna(5)
        results_df = results_df.sort_values('_trust_sort', ascending=True)
        results_df = results_df.drop_duplicates(subset=['account_number', 'service_id'], keep='first')
        results_df = results_df.drop(columns=['_trust_sort'])

        # Drop match_score column if present (internal use only)
        if 'match_score' in results_df.columns:
            results_df = results_df.drop(columns=['match_score'])

        stats['unique_mappings'] = len(results_df)

        # Reorder columns
        col_order = ['detected_vendor', 'account_number', 'service_id', 'billing_vendor',
                     'invoice_number', 'link_type']
        results_df = results_df[[c for c in col_order if c in results_df.columns]]

        results_df.to_csv(output_path, index=False)
        print(f"  Saved {stats['unique_mappings']:,} unique mappings to {output_path}")
    else:
        print("  WARNING: No results to save")

    # ==========================================================================
    # Summary
    # ==========================================================================
    print("\n" + "=" * 60)
    print("LINKAGE PIPELINE SUMMARY (v4 - Voucher-First)")
    print("=" * 60)
    print(f"\nSettings:")
    print(f"  Lookback days:          {lookback_days} {'(no limit)' if lookback_days == 0 else ''}")
    print(f"  Phase delay:            {phase_delay}s")
    print(f"  Voucher data:           {'PROVIDED' if voucher_dir else 'NOT PROVIDED (reduced accuracy)'}")
    print(f"\nInput:")
    print(f"  OCR invoices:           {stats['ocr_invoices']:,}")
    print(f"  With invoice numbers:   {stats['ocr_with_invoice_number']:,}")
    print(f"  Billing references:     {stats['billing_references']:,}")
    print(f"  Active services:        {stats['active_services']:,}")
    print(f"\nExtraction Coverage (for voucher matching):")
    ocr_with_ext = stats.get('ocr_with_extraction', 0)
    if stats['ocr_with_invoice_number'] > 0:
        ext_pct = 100 * ocr_with_ext / stats['ocr_with_invoice_number']
        print(f"  OCR with bill_total:    {ocr_with_ext:,} ({ext_pct:.1f}%)")
    else:
        print(f"  OCR with bill_total:    {ocr_with_ext:,}")
    print(f"\nBilling Reference Trust:")
    print(f"  Trustworthy (1 vendor): {stats['trustworthy_refs']:,}")
    print(f"  Untrustworthy (multi):  {stats['untrustworthy_refs']:,}")
    print(f"\nLink Types (by trust level):")
    print(f"  VOUCHER_VALIDATED:      {stats['voucher_validated']:,} (HIGHEST trust - correct flow)")
    print(f"  DIRECT_SINGLE_VENDOR:   {stats['direct_single_vendor']:,} (MEDIUM trust - single vendor ref)")
    print(f"  SUBSTRING_SINGLE_VENDOR:{stats['substring_single_vendor']:,} (MEDIUM trust - substring match)")
    print(f"  DIRECT_MULTI_VENDOR:    {stats['direct_multi_vendor']:,} (LOW trust - multi vendor ref)")
    print(f"  VOUCHER_ONLY:           {stats['voucher_only']:,} (no service link yet)")
    print(f"\nOutput:")
    print(f"  Unique mappings:        {stats['unique_mappings']:,}")

    if not voucher_dir:
        print("\n" + "!" * 60)
        print("WARNING: No voucher data provided!")
        print("Direct matching without voucher validation may have HIGH false positive rate.")
        print("Recommend: python -m ... --voucher-dir /path/to/voucher/files")
        print("!" * 60)

    return stats


if __name__ == '__main__':
    import argparse

    parser = argparse.ArgumentParser(
        description='Account Linkage Pipeline (v4 - Voucher-First)',
        epilog='''
IMPORTANT: This pipeline uses voucher data as the PRIMARY matching path.
Direct OCR → billing_reference matching is a FALLBACK with higher false positive rate.

Correct data flow (voucher-first):
  OCR ──fuzzy match──► Voucher ──► billing_reference ──► service_id
       (vendor+amount+date)    (ACTUAL invoice#)

Recommend always providing --voucher-dir for best results.
        '''
    )

    # Data sources
    parser.add_argument('--billing', help='Path to billing charges CSV (required if --azure-billing not used)')
    parser.add_argument('--azure-billing', action='store_true',
                        help='Query billing charges from Azure SQL instead of CSV file')
    parser.add_argument('--ocr', required=True, help='Path to OCR CSV with invoice_number (ocr_step3_invoices.csv)')
    parser.add_argument('--ocr-accounts', help='Path to OCR accounts CSV (ocr_step2_accounts.csv). Merged by md5_hash.')
    parser.add_argument('--output', required=True, help='Output path for lookup CSV')
    parser.add_argument('--voucher-dir', help='Directory with VoucherExport_*.csv files (RECOMMENDED for best accuracy)')

    # Matching options
    parser.add_argument('--no-substring', action='store_true', help='Disable substring matching')
    parser.add_argument('--no-active-filter', action='store_true', help='Disable active service filtering')

    # Azure SQL settings
    parser.add_argument('--sql-server', default='wasteology.database.windows.net', help='Azure SQL server')
    parser.add_argument('--sql-database', default='wasteology', help='Azure SQL database')

    # Performance tuning
    parser.add_argument('--lookback-days', type=int, default=120,
                        help='Only include billing charges from last N days (default: 120, 0=no limit)')
    parser.add_argument('--phase-delay', type=float, default=2.0,
                        help='Seconds to pause between phases (default: 2.0, 0=no delay)')

    args = parser.parse_args()

    # Validate: either --billing or --azure-billing must be provided
    if not args.azure_billing and not args.billing:
        parser.error("Either --billing <path> or --azure-billing is required")

    stats = run_linkage_pipeline(
        ocr_path=args.ocr,
        output_path=args.output,
        billing_path=args.billing,
        use_azure_billing=args.azure_billing,
        voucher_dir=args.voucher_dir,
        use_substring_matching=not args.no_substring,
        ocr_accounts_path=args.ocr_accounts,
        filter_active_services=not args.no_active_filter,
        sql_server=args.sql_server,
        sql_database=args.sql_database,
        lookback_days=args.lookback_days,
        phase_delay=args.phase_delay
    )

    print("\n=== STATS ===")
    for key, value in stats.items():
        print(f"  {key}: {value:,}")
