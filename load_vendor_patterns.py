"""
Load big-4 vendor regex patterns into ip_vendor_pattern.

Decomposes the procedural Python extraction functions from parsing_engines/
into individual pattern rows with scan metadata.

Vendors: Republic Services, Waste Management, GFL, Anytime Waste
Fields:  vendor_detection, account_number, invoice_number, invoice_date,
         charge_line_item

Usage:
    python -m src load-patterns          # truncate + reload (idempotent)
    python -m src load-patterns --dry-run  # validate only
"""

import json
import logging
import re

import psycopg2.extras

from .database import get_cursor

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Pattern definitions — hand-decomposed from parsing_engines source functions
# ---------------------------------------------------------------------------

VENDOR_PATTERNS = [
    # ===================================================================
    # VENDOR DETECTION  (4 rows)
    # ===================================================================
    {
        'vendor_name': 'Republic Services',
        'field': 'vendor_detection',
        'format_variant': 1,
        'pattern_type': 'PRIMARY',
        'priority': 10,
        'regex_pattern': r'REPUBLIC\s*SERVICES',
        'regex_flags': 'IGNORECASE',
        'capture_group': 0,
        'normalization': 'NONE',
        'scan_type': 'INLINE',
        'scan_lines': 1,
        'date_format': None,
        'is_no_account': False,
        'notes': 'vendor_detection_module_v9.py line 266',
    },
    {
        'vendor_name': 'Waste Management',
        'field': 'vendor_detection',
        'format_variant': 1,
        'pattern_type': 'PRIMARY',
        'priority': 10,
        'regex_pattern': r'WASTE\s*MANAGEMENT',
        'regex_flags': 'IGNORECASE',
        'capture_group': 0,
        'normalization': 'NONE',
        'scan_type': 'INLINE',
        'scan_lines': 1,
        'date_format': None,
        'is_no_account': False,
        'notes': 'vendor_detection_module_v9.py line 318',
    },
    {
        'vendor_name': 'GFL',
        'field': 'vendor_detection',
        'format_variant': 1,
        'pattern_type': 'PRIMARY',
        'priority': 10,
        'regex_pattern': r'\bGFL\b\s*(ENVIRONMENTAL|GREEN\s*FOR\s*LIFE)?',
        'regex_flags': 'IGNORECASE',
        'capture_group': 0,
        'normalization': 'NONE',
        'scan_type': 'INLINE',
        'scan_lines': 1,
        'date_format': None,
        'is_no_account': False,
        'notes': 'vendor_detection_module_v9.py line 184; word boundary to avoid WG Waste false positive',
    },
    {
        'vendor_name': 'Anytime Waste',
        'field': 'vendor_detection',
        'format_variant': 1,
        'pattern_type': 'PRIMARY',
        'priority': 10,
        'regex_pattern': r'ANYTIME\s*WASTE',
        'regex_flags': 'IGNORECASE',
        'capture_group': 0,
        'normalization': 'NONE',
        'scan_type': 'INLINE',
        'scan_lines': 1,
        'date_format': None,
        'is_no_account': False,
        'notes': 'vendor_detection_module_v9.py line 121',
    },

    # ===================================================================
    # ACCOUNT NUMBER  (9 rows)
    # ===================================================================

    # --- Republic Services (1 pattern) ---
    {
        'vendor_name': 'Republic Services',
        'field': 'account_number',
        'format_variant': 1,
        'pattern_type': 'PRIMARY',
        'priority': 10,
        'regex_pattern': r'(\d-\d{4}-\d{7})',
        'regex_flags': 'NONE',
        'capture_group': 1,
        'normalization': 'NONE',
        'scan_type': 'INLINE',
        'scan_lines': 1,
        'date_format': None,
        'is_no_account': False,
        'notes': 'Format: D-DDDD-DDDDDDD (e.g. 3-0509-0312663). Full-text re.search.',
    },

    # --- Waste Management (3 patterns) ---
    {
        'vendor_name': 'Waste Management',
        'field': 'account_number',
        'format_variant': 1,
        'pattern_type': 'PRIMARY',
        'priority': 10,
        'regex_pattern': r'(W(?:GY|HM)[A-Z0-9]{5,8})',
        'regex_flags': 'NONE',
        'capture_group': 1,
        'normalization': 'NONE',
        'scan_type': 'INLINE',
        'scan_lines': 1,
        'date_format': None,
        'is_no_account': False,
        'notes': 'WGY/WHM prefix format (e.g. WGY17110UB). Full-text re.search.',
    },
    {
        'vendor_name': 'Waste Management',
        'field': 'account_number',
        'format_variant': 1,
        'pattern_type': 'PRIMARY',
        'priority': 20,
        'regex_pattern': r'\b(\d{2}-\d{5}-\d{5})\b',
        'regex_flags': 'NONE',
        'capture_group': 1,
        'normalization': 'NONE',
        'scan_type': 'FORWARD_COLUMNAR',
        'scan_lines': 3,
        'date_format': None,
        'is_no_account': False,
        'notes': 'Alternate format NN-NNNNN-NNNNN after "Customer ID" label. Scan 3 lines.',
    },
    {
        'vendor_name': 'Waste Management',
        'field': 'account_number',
        'format_variant': 1,
        'pattern_type': 'FALLBACK',
        'priority': 30,
        'regex_pattern': r'Customer\s*#:\s*(\d{2}-\d{5}\s*\d?)',
        'regex_flags': 'NONE',
        'capture_group': 1,
        'normalization': 'STRIP_WHITESPACE',
        'scan_type': 'INLINE',
        'scan_lines': 1,
        'date_format': None,
        'is_no_account': False,
        'notes': 'Westside variant "Customer #: NN-NNNNN N". Full-text re.search.',
    },

    # --- GFL (2 patterns) ---
    {
        'vendor_name': 'GFL',
        'field': 'account_number',
        'format_variant': 1,
        'pattern_type': 'PRIMARY',
        'priority': 10,
        'regex_pattern': r'ACCOUNT\s*NUMBER:\s*(\d{9})',
        'regex_flags': 'IGNORECASE',
        'capture_group': 1,
        'normalization': 'NONE',
        'scan_type': 'INLINE',
        'scan_lines': 1,
        'date_format': None,
        'is_no_account': False,
        'notes': 'Inline "ACCOUNT NUMBER: NNNNNNNNN". Full-text re.search.',
    },
    {
        'vendor_name': 'GFL',
        'field': 'account_number',
        'format_variant': 1,
        'pattern_type': 'PRIMARY',
        'priority': 20,
        'regex_pattern': r'\b([A-Z]{1,2}\d{4,8}|\d{9})\b',
        'regex_flags': 'NONE',
        'capture_group': 1,
        'normalization': 'NONE',
        'scan_type': 'FORWARD_COLUMNAR',
        'scan_lines': 6,
        'date_format': None,
        'is_no_account': False,
        'notes': 'After "CUSTOMER #" or "ACCOUNT #" label. Scan 6 lines. Format: XX######(#) or 9-digit.',
    },

    # --- Anytime Waste (3 patterns) ---
    {
        'vendor_name': 'Anytime Waste',
        'field': 'account_number',
        'format_variant': 1,
        'pattern_type': 'PRIMARY',
        'priority': 10,
        'regex_pattern': r'^\d{5}$',
        'regex_flags': 'NONE',
        'capture_group': 0,
        'normalization': 'NONE',
        'scan_type': 'INLINE',
        'scan_lines': 1,
        'date_format': None,
        'is_no_account': False,
        'notes': 'NavuSoft 5-digit account at line 0 (re.match on first line).',
    },
    {
        'vendor_name': 'Anytime Waste',
        'field': 'account_number',
        'format_variant': 1,
        'pattern_type': 'PRIMARY',
        'priority': 20,
        'regex_pattern': r'^\d{5}$',
        'regex_flags': 'NONE',
        'capture_group': 0,
        'normalization': 'NONE',
        'scan_type': 'FORWARD_COLUMNAR',
        'scan_lines': 5,
        'date_format': None,
        'is_no_account': False,
        'notes': 'After "ACCOUNT #" header, scan 5 lines for standalone 5-digit number.',
    },
    {
        'vendor_name': 'Anytime Waste',
        'field': 'account_number',
        'format_variant': 1,
        'pattern_type': 'FALLBACK',
        'priority': 30,
        'regex_pattern': r'^\d{5}$',
        'regex_flags': 'NONE',
        'capture_group': 0,
        'normalization': 'NONE',
        'scan_type': 'INLINE',
        'scan_lines': 1,
        'date_format': None,
        'is_no_account': False,
        'notes': 'Fixed position fallback: check line 4 for 5-digit number.',
    },

    # ===================================================================
    # INVOICE NUMBER  (10 rows)
    # ===================================================================

    # --- Republic Services (2 patterns) ---
    {
        'vendor_name': 'Republic Services',
        'field': 'invoice_number',
        'format_variant': 1,
        'pattern_type': 'PRIMARY',
        'priority': 10,
        'regex_pattern': r'(\d{4}-\d{9})',
        'regex_flags': 'NONE',
        'capture_group': 1,
        'normalization': 'NONE',
        'scan_type': 'INLINE',
        'scan_lines': 1,
        'date_format': None,
        'is_no_account': False,
        'notes': 'Format DDDD-NNNNNNNNN (e.g. 0176-007823583). Full-text re.search.',
    },
    {
        'vendor_name': 'Republic Services',
        'field': 'invoice_number',
        'format_variant': 1,
        'pattern_type': 'FALLBACK',
        'priority': 20,
        'regex_pattern': r'(\d{4}-\d{9})',
        'regex_flags': 'NONE',
        'capture_group': 1,
        'normalization': 'NONE',
        'scan_type': 'FORWARD_COLUMNAR',
        'scan_lines': 5,
        'date_format': None,
        'is_no_account': False,
        'notes': 'After "Invoice Number" header, scan 5 lines.',
    },

    # --- Waste Management (3 patterns) ---
    {
        'vendor_name': 'Waste Management',
        'field': 'invoice_number',
        'format_variant': 2,
        'pattern_type': 'PRIMARY',
        'priority': 10,
        'regex_pattern': r'^\d{7}-\d{4}-\d$',
        'regex_flags': 'NONE',
        'capture_group': 0,
        'normalization': 'NONE',
        'scan_type': 'FORWARD_COLUMNAR',
        'scan_lines': 6,
        'date_format': None,
        'is_no_account': False,
        'notes': 'WM Solutions format NNNNNNN-NNNN-N. After "Invoice Number" header, scan lines i+3 to i+6.',
    },
    {
        'vendor_name': 'Waste Management',
        'field': 'invoice_number',
        'format_variant': 1,
        'pattern_type': 'PRIMARY',
        'priority': 20,
        'regex_pattern': r'INVOICE\s*NUMBER:?\s*(\d{10})',
        'regex_flags': 'IGNORECASE',
        'capture_group': 1,
        'normalization': 'NONE',
        'scan_type': 'INLINE',
        'scan_lines': 1,
        'date_format': None,
        'is_no_account': False,
        'notes': 'Standard 10-digit inline format. Also scans 5 lines after label for standalone ^\\d{10}$.',
    },
    {
        'vendor_name': 'Waste Management',
        'field': 'invoice_number',
        'format_variant': 1,
        'pattern_type': 'FALLBACK',
        'priority': 30,
        'regex_pattern': r'Invoice\s*(?:Number|#|No\.?)?:?\s*(\d{10})',
        'regex_flags': 'IGNORECASE',
        'capture_group': 1,
        'normalization': 'NONE',
        'scan_type': 'INLINE',
        'scan_lines': 1,
        'date_format': None,
        'is_no_account': False,
        'notes': 'Broad fallback on normalized text. Matches "Invoice Number:", "Invoice #:", "Invoice No:".',
    },

    # --- GFL (4 patterns) ---
    {
        'vendor_name': 'GFL',
        'field': 'invoice_number',
        'format_variant': 1,
        'pattern_type': 'PRIMARY',
        'priority': 10,
        'regex_pattern': r'INVOICE\s*NUMBER:\s*(\d{10})',
        'regex_flags': 'IGNORECASE',
        'capture_group': 1,
        'normalization': 'NONE',
        'scan_type': 'INLINE',
        'scan_lines': 1,
        'date_format': None,
        'is_no_account': False,
        'notes': 'Inline "INVOICE NUMBER: NNNNNNNNNN". Full-text re.search on normalized text.',
    },
    {
        'vendor_name': 'GFL',
        'field': 'invoice_number',
        'format_variant': 1,
        'pattern_type': 'PRIMARY',
        'priority': 20,
        'regex_pattern': r'^[A-Z]{1,2}\d{10,11}$',
        'regex_flags': 'NONE',
        'capture_group': 0,
        'normalization': 'NONE',
        'scan_type': 'WIDE_COLUMNAR',
        'scan_lines': 7,
        'date_format': None,
        'is_no_account': False,
        'notes': 'After "INVOICE #:" header, scan lines i+4 to i+7 for prefix+digits (e.g. UK0000449634).',
    },
    {
        'vendor_name': 'GFL',
        'field': 'invoice_number',
        'format_variant': 1,
        'pattern_type': 'PRIMARY',
        'priority': 30,
        'regex_pattern': r'INVOICE\s*#:?\s*([A-Z]{0,2}\d{8,11})',
        'regex_flags': 'IGNORECASE',
        'capture_group': 1,
        'normalization': 'NONE',
        'scan_type': 'FORWARD_COLUMNAR',
        'scan_lines': 5,
        'date_format': None,
        'is_no_account': False,
        'notes': 'After "INVOICE #" header: inline match on same line, then scan 5 lines for ^[A-Z]{0,2}\\d{8,11}$.',
    },
    {
        'vendor_name': 'GFL',
        'field': 'invoice_number',
        'format_variant': 1,
        'pattern_type': 'FALLBACK',
        'priority': 40,
        'regex_pattern': r'\b([A-Z]{2}\d{10})\b',
        'regex_flags': 'NONE',
        'capture_group': 1,
        'normalization': 'NONE',
        'scan_type': 'INLINE',
        'scan_lines': 1,
        'date_format': None,
        'is_no_account': False,
        'notes': 'Direct 2-letter prefix + 10 digits pattern (e.g. UK0000449634). Full-text fallback.',
    },

    # --- Anytime Waste (1 pattern, NavuSoft) ---
    {
        'vendor_name': 'Anytime Waste',
        'field': 'invoice_number',
        'format_variant': 1,
        'pattern_type': 'PRIMARY',
        'priority': 10,
        'regex_pattern': r'^\d{6}$',
        'regex_flags': 'NONE',
        'capture_group': 0,
        'normalization': 'NONE',
        'scan_type': 'INLINE',
        'scan_lines': 1,
        'date_format': None,
        'is_no_account': False,
        'notes': 'NavuSoft 6-digit invoice at line 0 (re.match on first line).',
    },
    {
        'vendor_name': 'Anytime Waste',
        'field': 'invoice_number',
        'format_variant': 1,
        'pattern_type': 'PRIMARY',
        'priority': 20,
        'regex_pattern': r'INVOICE\s*#:?\s*(\d{6})',
        'regex_flags': 'IGNORECASE',
        'capture_group': 1,
        'normalization': 'NONE',
        'scan_type': 'FORWARD_COLUMNAR',
        'scan_lines': 5,
        'date_format': None,
        'is_no_account': False,
        'notes': 'After "INVOICE #" header: inline match, then scan 5 lines for standalone ^\\d{6}$.',
    },

    # ===================================================================
    # INVOICE DATE  (20 rows)
    # ===================================================================

    # --- Republic Services (3 patterns) ---
    {
        'vendor_name': 'Republic Services',
        'field': 'invoice_date',
        'format_variant': 1,
        'pattern_type': 'PRIMARY',
        'priority': 10,
        'regex_pattern': r'INVOICE\s*DATE[:\s]+(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})',
        'regex_flags': 'IGNORECASE',
        'capture_group': 1,
        'normalization': 'NONE',
        'scan_type': 'INLINE',
        'scan_lines': 1,
        'date_format': 'MDY',
        'is_no_account': False,
        'notes': 'Inline "INVOICE DATE: MM/DD/YYYY". Full-text re.search.',
    },
    {
        'vendor_name': 'Republic Services',
        'field': 'invoice_date',
        'format_variant': 1,
        'pattern_type': 'PRIMARY',
        'priority': 20,
        'regex_pattern': r'^(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})$',
        'regex_flags': 'NONE',
        'capture_group': 1,
        'normalization': 'NONE',
        'scan_type': 'WIDE_COLUMNAR',
        'scan_lines': 12,
        'date_format': 'MDY',
        'is_no_account': False,
        'notes': 'Wide columnar: INVOICE DATE label then date value 1-12 lines below.',
    },
    {
        'vendor_name': 'Republic Services',
        'field': 'invoice_date',
        'format_variant': 1,
        'pattern_type': 'FALLBACK',
        'priority': 30,
        'regex_pattern': r'BILL\s*DATE[:\s]+(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})',
        'regex_flags': 'IGNORECASE',
        'capture_group': 1,
        'normalization': 'NONE',
        'scan_type': 'INLINE',
        'scan_lines': 1,
        'date_format': 'MDY',
        'is_no_account': False,
        'notes': 'Fallback to BILL DATE label. Full-text re.search.',
    },

    # --- Waste Management (8 patterns) ---
    {
        'vendor_name': 'Waste Management',
        'field': 'invoice_date',
        'format_variant': 1,
        'pattern_type': 'PRIMARY',
        'priority': 10,
        'regex_pattern': r'^\s*DATE\s*$',
        'regex_flags': 'IGNORECASE',
        'capture_group': 0,
        'normalization': 'NONE',
        'scan_type': 'FORWARD_COLUMNAR',
        'scan_lines': 3,
        'date_format': 'MDY',
        'is_no_account': False,
        'notes': 'Bare "DATE" label on its own line. Scan 3 lines for ^MM/DD/YYYY$. Most common WM format.',
    },
    {
        'vendor_name': 'Waste Management',
        'field': 'invoice_date',
        'format_variant': 1,
        'pattern_type': 'PRIMARY',
        'priority': 15,
        'regex_pattern': r'^DATE\s+(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})',
        'regex_flags': 'NONE',
        'capture_group': 1,
        'normalization': 'NONE',
        'scan_type': 'INLINE',
        'scan_lines': 1,
        'date_format': 'MDY',
        'is_no_account': False,
        'notes': 'DATE and value on same line (e.g. "DATE 01/15/2025"). re.match on stripped line.',
    },
    {
        'vendor_name': 'Waste Management',
        'field': 'invoice_date',
        'format_variant': 1,
        'pattern_type': 'PRIMARY',
        'priority': 20,
        'regex_pattern': r'INVOICE\s*DATE[:\s]+([A-Za-z]+)\s+(\d{1,2}),?\s*(\d{4})',
        'regex_flags': 'IGNORECASE',
        'capture_group': 1,
        'normalization': 'NONE',
        'scan_type': 'INLINE',
        'scan_lines': 1,
        'date_format': 'MONTH_NAME',
        'is_no_account': False,
        'notes': 'Inline "INVOICE DATE: January 15, 2025". Full-text re.search.',
    },
    {
        'vendor_name': 'Waste Management',
        'field': 'invoice_date',
        'format_variant': 1,
        'pattern_type': 'PRIMARY',
        'priority': 25,
        'regex_pattern': r'INVOICE\s*DATE[:\s]+(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})',
        'regex_flags': 'IGNORECASE',
        'capture_group': 1,
        'normalization': 'NONE',
        'scan_type': 'INLINE',
        'scan_lines': 1,
        'date_format': 'MDY',
        'is_no_account': False,
        'notes': 'Inline "INVOICE DATE: MM/DD/YYYY". Full-text re.search.',
    },
    {
        'vendor_name': 'Waste Management',
        'field': 'invoice_date',
        'format_variant': 1,
        'pattern_type': 'FALLBACK',
        'priority': 30,
        'regex_pattern': r'BILL\s*DATE[:\s]+(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})',
        'regex_flags': 'IGNORECASE',
        'capture_group': 1,
        'normalization': 'NONE',
        'scan_type': 'INLINE',
        'scan_lines': 1,
        'date_format': 'MDY',
        'is_no_account': False,
        'notes': 'Fallback BILL DATE label.',
    },
    {
        'vendor_name': 'Waste Management',
        'field': 'invoice_date',
        'format_variant': 1,
        'pattern_type': 'FALLBACK',
        'priority': 35,
        'regex_pattern': r'BILLING\s*DATE[:\s]+(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})',
        'regex_flags': 'IGNORECASE',
        'capture_group': 1,
        'normalization': 'NONE',
        'scan_type': 'INLINE',
        'scan_lines': 1,
        'date_format': 'MDY',
        'is_no_account': False,
        'notes': 'Fallback BILLING DATE label.',
    },
    {
        'vendor_name': 'Waste Management',
        'field': 'invoice_date',
        'format_variant': 1,
        'pattern_type': 'FALLBACK',
        'priority': 40,
        'regex_pattern': r'SERVICE\s*PERIOD[:\s]+(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})',
        'regex_flags': 'IGNORECASE',
        'capture_group': 1,
        'normalization': 'NONE',
        'scan_type': 'INLINE',
        'scan_lines': 1,
        'date_format': 'MDY',
        'is_no_account': False,
        'notes': 'Fallback SERVICE PERIOD label (takes start date of period).',
    },
    {
        'vendor_name': 'Waste Management',
        'field': 'invoice_date',
        'format_variant': 1,
        'pattern_type': 'FALLBACK',
        'priority': 45,
        'regex_pattern': r'^(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})$',
        'regex_flags': 'NONE',
        'capture_group': 1,
        'normalization': 'NONE',
        'scan_type': 'FORWARD_COLUMNAR',
        'scan_lines': 1,
        'date_format': 'MDY',
        'is_no_account': False,
        'notes': 'Multiline fallback: INVOICE DATE label then date on very next line.',
    },

    # --- GFL (6 patterns) ---
    {
        'vendor_name': 'GFL',
        'field': 'invoice_date',
        'format_variant': 1,
        'pattern_type': 'PRIMARY',
        'priority': 10,
        'regex_pattern': r'INVOICE\s*DATE[:\s]+(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})',
        'regex_flags': 'IGNORECASE',
        'capture_group': 1,
        'normalization': 'NONE',
        'scan_type': 'INLINE',
        'scan_lines': 1,
        'date_format': 'MDY',
        'is_no_account': False,
        'notes': 'Inline "INVOICE DATE: MM/DD/YYYY". Full-text re.search.',
    },
    {
        'vendor_name': 'GFL',
        'field': 'invoice_date',
        'format_variant': 1,
        'pattern_type': 'PRIMARY',
        'priority': 20,
        'regex_pattern': r'^(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})',
        'regex_flags': 'NONE',
        'capture_group': 1,
        'normalization': 'NONE',
        'scan_type': 'WIDE_COLUMNAR',
        'scan_lines': 15,
        'date_format': 'MDY',
        'is_no_account': False,
        'notes': 'Wide columnar: INVOICE DATE label then numeric date 1-15 lines below. GFL header block.',
    },
    {
        'vendor_name': 'GFL',
        'field': 'invoice_date',
        'format_variant': 1,
        'pattern_type': 'PRIMARY',
        'priority': 25,
        'regex_pattern': r'(\d{1,2})[-\s](Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\w*[-\s,]*(\d{4})',
        'regex_flags': 'IGNORECASE',
        'capture_group': 1,
        'normalization': 'NONE',
        'scan_type': 'WIDE_COLUMNAR',
        'scan_lines': 15,
        'date_format': 'DD_MON_YYYY',
        'is_no_account': False,
        'notes': 'Wide columnar DD-Mon-YYYY (e.g. 31-Aug-2025). GFL Morristown/Lakeland offices.',
    },
    {
        'vendor_name': 'GFL',
        'field': 'invoice_date',
        'format_variant': 1,
        'pattern_type': 'PRIMARY',
        'priority': 30,
        'regex_pattern': r'^(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})$',
        'regex_flags': 'NONE',
        'capture_group': 1,
        'normalization': 'NONE',
        'scan_type': 'REVERSE_COLUMNAR',
        'scan_lines': 5,
        'date_format': 'MDY',
        'is_no_account': False,
        'notes': 'Reverse columnar: date value ABOVE "INVOICE DATE" label. Scan 5 lines up.',
    },
    {
        'vendor_name': 'GFL',
        'field': 'invoice_date',
        'format_variant': 1,
        'pattern_type': 'FALLBACK',
        'priority': 40,
        'regex_pattern': r'^(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})$',
        'regex_flags': 'NONE',
        'capture_group': 1,
        'normalization': 'NONE',
        'scan_type': 'FORWARD_COLUMNAR',
        'scan_lines': 10,
        'date_format': 'MDY',
        'is_no_account': False,
        'notes': 'Bare "DATE" label fallback. Scan 10 lines forward for numeric or DD-Mon-YYYY.',
    },
    {
        'vendor_name': 'GFL',
        'field': 'invoice_date',
        'format_variant': 1,
        'pattern_type': 'FALLBACK',
        'priority': 50,
        'regex_pattern': r'\bDATE[:\s]+(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})',
        'regex_flags': 'IGNORECASE',
        'capture_group': 1,
        'normalization': 'NONE',
        'scan_type': 'INLINE',
        'scan_lines': 1,
        'date_format': 'MDY',
        'is_no_account': False,
        'notes': 'Inline "DATE: MM/DD/YYYY" last-resort fallback.',
    },

    # --- Anytime Waste (3 patterns) ---
    {
        'vendor_name': 'Anytime Waste',
        'field': 'invoice_date',
        'format_variant': 1,
        'pattern_type': 'PRIMARY',
        'priority': 10,
        'regex_pattern': r'^\s*([A-Za-z]+)\s+(\d{1,2}),?\s*(\d{4})\s*$',
        'regex_flags': 'NONE',
        'capture_group': 1,
        'normalization': 'NONE',
        'scan_type': 'WIDE_COLUMNAR',
        'scan_lines': 12,
        'date_format': 'MONTH_NAME',
        'is_no_account': False,
        'notes': 'NavuSoft: bare DATE label then "April 30, 2025" 1-12 lines below (address block in between).',
    },
    {
        'vendor_name': 'Anytime Waste',
        'field': 'invoice_date',
        'format_variant': 1,
        'pattern_type': 'PRIMARY',
        'priority': 20,
        'regex_pattern': r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$',
        'regex_flags': 'NONE',
        'capture_group': 1,
        'normalization': 'NONE',
        'scan_type': 'WIDE_COLUMNAR',
        'scan_lines': 12,
        'date_format': 'MDY',
        'is_no_account': False,
        'notes': 'NavuSoft: bare DATE label then numeric date 1-12 lines below.',
    },
    {
        'vendor_name': 'Anytime Waste',
        'field': 'invoice_date',
        'format_variant': 1,
        'pattern_type': 'FALLBACK',
        'priority': 30,
        'regex_pattern': r'\bDATE[:\s]+([A-Za-z]+)\s+(\d{1,2}),?\s*(\d{4})',
        'regex_flags': 'IGNORECASE',
        'capture_group': 1,
        'normalization': 'NONE',
        'scan_type': 'INLINE',
        'scan_lines': 1,
        'date_format': 'MONTH_NAME',
        'is_no_account': False,
        'notes': 'Inline "DATE: April 30, 2025" fallback.',
    },

    # ===================================================================
    # CHARGE LINE ITEM  (31 rows — multi-match, execution_mode='MULTI')
    # ===================================================================

    # --- Republic Services (8 patterns) ---
    {
        'vendor_name': 'Republic Services',
        'field': 'charge_line_item',
        'format_variant': 1,
        'pattern_type': 'PRIMARY',
        'priority': 10,
        'regex_pattern': (
            r'(?P<desc>\d+\s+Container\(?s?\)?\s+[\d.]+\s*'
            r'(?:Yard|YD|Gallon)[\w\s,]+?'
            r'(?:Per\s+(?:Week|Month|Pickup)))\s*\n'
            r'(?P<svc>[^\n]+?(?:Service|Charge|Fee|Surcharge))\s+'
            r'(?:\d{1,2}/\d{1,2}/\d{2,4}\s*-\s*\d{1,2}/\d{1,2}/\d{2,4}\s+)?'
            r'\$?(?P<rate>[\d,]+\.?\d*)\s+'
            r'\$?(?P<amount>-?[\d,]+\.?\d*)'
        ),
        'regex_flags': 'IGNORECASE',
        'capture_group': 0,
        'normalization': 'NONE',
        'scan_type': 'INLINE',
        'scan_lines': 1,
        'date_format': None,
        'is_no_account': False,
        'execution_mode': 'MULTI',
        'capture_map': json.dumps({'desc': 'charge_description', 'svc': 'charge_description',
                                    'rate': 'unit_price', 'amount': 'amount'}),
        'pattern_tier': 'TIER_1',
        'activation_condition': None,
        'description_template': '{desc} - {svc}',
        'notes': 'Republic 2-line container+service pattern. charge_code_engine.py container_pat.',
    },
    # NOTE: Republic P15 (container header) REMOVED — captures desc only, no amount.
    # Republic OCR renders tables as column blocks (descriptions first, amounts later).
    # A desc-only match causes false "engine hit" with $0 charges.
    {
        'vendor_name': 'Republic Services',
        'field': 'charge_line_item',
        'format_variant': 1,
        'pattern_type': 'PRIMARY',
        'priority': 20,
        'regex_pattern': (
            r'(?P<desc>Pickup\s+Service|Rental|Donation|Disposal|Gate\s+Charge|'
            r'Pull-?Out\s+Charge|Lock\s+Charge|Hazardous\s+Waste\s+Fee|'
            r'Waste/Recycling\s+Overage|Overload\s+Charge|'
            r'[\w\s]+Tax|[\w\s]+Fee|[\w\s]+Surcharge|[\w\s]+Surchg)\s*'
            r'(?:\d{1,2}/\d{1,2}\s*[-\u2013]\s*\d{1,2}/\d{1,2})?\s*'
            r'(?P<qty>[\d.]+)?\s*'
            r'-?\$(?P<price>[\d,]+\.?\d*)\s*'
            r'-?\$(?P<amount>[\d,]+\.?\d*)'
        ),
        'regex_flags': 'IGNORECASE',
        'capture_group': 0,
        'normalization': 'NONE',
        'scan_type': 'INLINE',
        'scan_lines': 1,
        'date_format': None,
        'is_no_account': False,
        'execution_mode': 'MULTI',
        'capture_map': json.dumps({'desc': 'charge_description', 'qty': 'qty',
                                    'price': 'unit_price', 'amount': 'amount'}),
        'pattern_tier': 'TIER_1',
        'activation_condition': None,
        'description_template': None,
        'notes': 'Republic service line with qty/price/amount. configured.py service_pattern.',
    },
    {
        'vendor_name': 'Republic Services',
        'field': 'charge_line_item',
        'format_variant': 1,
        'pattern_type': 'PRIMARY',
        'priority': 30,
        'regex_pattern': (
            r'(?P<desc>(?:Delivery|Removal|Extra|Admin|Container|Fuel|Enviro|Disposal|'
            r'Recycl\w*|Franchise|Regulatory|Lock|Lid|Over[\w]*|Contamination)[\w\s\-/]+?)\s+'
            r'(?:\d{1,2}/\d{1,2}/\d{2,4}\s*-\s*\d{1,2}/\d{1,2}/\d{2,4}\s+)?'
            r'\$?(?P<rate>[\d,]+\.?\d*)\s+'
            r'\$?(?P<amount>-?[\d,]+\.?\d*)'
        ),
        'regex_flags': 'IGNORECASE',
        'capture_group': 0,
        'normalization': 'NONE',
        'scan_type': 'INLINE',
        'scan_lines': 1,
        'date_format': None,
        'is_no_account': False,
        'execution_mode': 'MULTI',
        'capture_map': json.dumps({'desc': 'charge_description', 'rate': 'unit_price',
                                    'amount': 'amount'}),
        'pattern_tier': 'TIER_2',
        'activation_condition': None,
        'description_template': None,
        'notes': 'Republic service/charge lines with optional date range. charge_code_engine.py svc_pat.',
    },
    {
        'vendor_name': 'Republic Services',
        'field': 'charge_line_item',
        'format_variant': 1,
        'pattern_type': 'PRIMARY',
        'priority': 35,
        'regex_pattern': (
            r'(?P<desc>Gate\s+Charge|Pull-?Out\s+Charge|Hazardous\s+Waste\s+Fee|'
            r'Lock\s+Charge|Admin\s+Fee|Environmental\s+Fee|Late\s+Fee|'
            r'Total\s+[\w\s]+(?:Tax|Fee|Surchg|Surcharge))\s*'
            r'(?:\d{1,2}/\d{1,2}(?:\s*[-\u2013]\s*\d{1,2}/\d{1,2})?)?\s*'
            r'(?:[\d.]+\s+)?'
            r'\$(?P<amount>[\d,]+\.?\d*)'
        ),
        'regex_flags': 'IGNORECASE',
        'capture_group': 0,
        'normalization': 'NONE',
        'scan_type': 'INLINE',
        'scan_lines': 1,
        'date_format': None,
        'is_no_account': False,
        'execution_mode': 'MULTI',
        'capture_map': json.dumps({'desc': 'charge_description', 'amount': 'amount'}),
        'pattern_tier': 'TIER_2',
        'activation_condition': None,
        'description_template': None,
        'notes': 'Republic named fee lines (Gate, Lock, Late, etc). configured.py fee_pattern.',
    },
    {
        'vendor_name': 'Republic Services',
        'field': 'charge_line_item',
        'format_variant': 1,
        'pattern_type': 'PRIMARY',
        'priority': 40,
        'regex_pattern': (
            r'(?P<desc>(?:Fuel|Energy|Environmental|Franchise|Admin|Regulatory|Recovery|'
            r'Sustainability|Late)\s*(?:Surcharge|Fee|Charge|Recovery))\s+'
            r'\$?(?P<amount>[\d,]+\.?\d*)'
        ),
        'regex_flags': 'IGNORECASE',
        'capture_group': 0,
        'normalization': 'NONE',
        'scan_type': 'INLINE',
        'scan_lines': 1,
        'date_format': None,
        'is_no_account': False,
        'execution_mode': 'MULTI',
        'capture_map': json.dumps({'desc': 'charge_description', 'amount': 'amount'}),
        'pattern_tier': 'TIER_2',
        'activation_condition': None,
        'description_template': None,
        'notes': 'Republic simple surcharge lines. charge_code_engine.py fee_pat.',
    },
    {
        'vendor_name': 'Republic Services',
        'field': 'charge_line_item',
        'format_variant': 1,
        'pattern_type': 'PRIMARY',
        'priority': 45,
        'regex_pattern': (
            r'(?P<count>\d+)\s+Front\s+Load\s+(?P<size>[\d.]+)\s*(?:Yd|Gal)[,\s]*'
            r'(?P<freq>[^\n$]+)'
        ),
        'regex_flags': 'IGNORECASE',
        'capture_group': 0,
        'normalization': 'NONE',
        'scan_type': 'INLINE',
        'scan_lines': 1,
        'date_format': None,
        'is_no_account': False,
        'execution_mode': 'MULTI',
        'capture_map': json.dumps({'count': 'qty', 'size': 'charge_description',
                                    'freq': 'charge_description'}),
        'pattern_tier': 'TIER_2',
        'activation_condition': None,
        'description_template': '{count} Front Load {size} - {freq}',
        'notes': 'Republic Front Load container format. configured.py front_load_pattern.',
    },
    {
        'vendor_name': 'Republic Services',
        'field': 'charge_line_item',
        'format_variant': 1,
        'pattern_type': 'FALLBACK',
        'priority': 90,
        'regex_pattern': r'(?:Total\s+Amount\s+Due|Invoice\s+Charges)\s*\$?(?P<amt>[\d,]+\.?\d*)',
        'regex_flags': 'IGNORECASE',
        'capture_group': 0,
        'normalization': 'NONE',
        'scan_type': 'INLINE',
        'scan_lines': 1,
        'date_format': None,
        'is_no_account': False,
        'execution_mode': 'MULTI',
        'capture_map': json.dumps({'amt': 'amount'}),
        'pattern_tier': 'TIER_FALLBACK',
        'activation_condition': None,
        'description_template': None,
        'notes': 'Republic total amount fallback. Only fires if no TIER_1/TIER_2 matched.',
    },

    # --- Waste Management (9 patterns) ---
    {
        'vendor_name': 'Waste Management',
        'field': 'charge_line_item',
        'format_variant': 1,
        'pattern_type': 'PRIMARY',
        'priority': 5,
        'regex_pattern': (
            r'(?P<desc>Roll-?Off\s+[\w\s&]+|MSW|Haul|Disposal|Delivery)\s*'
            r'(?:W/O\s*#?:?\s*\d+)?\s*\n?(?:MSW|TRASH|RECYC\w*)?\s*\n?'
            r'\$(?P<rate>[\d,]+\.?\d*)\s*\n?(?P<qty>[\d.]+)\s*\n?'
            r'\$(?P<amount>[\d,]+\.?\d*)'
        ),
        'regex_flags': 'IGNORECASE',
        'capture_group': 0,
        'normalization': 'NONE',
        'scan_type': 'INLINE',
        'scan_lines': 1,
        'date_format': None,
        'is_no_account': False,
        'execution_mode': 'MULTI',
        'capture_map': json.dumps({'desc': 'charge_description', 'rate': 'unit_price',
                                    'qty': 'qty', 'amount': 'amount'}),
        'pattern_tier': 'TIER_1',
        'activation_condition': 'WIN Waste',
        'description_template': None,
        'notes': 'WM WIN Waste subsidiary format. charge_code_engine.py win_pat.',
    },
    {
        'vendor_name': 'Waste Management',
        'field': 'charge_line_item',
        'format_variant': 1,
        'pattern_type': 'PRIMARY',
        'priority': 6,
        'regex_pattern': (
            r'(?P<date>\d{1,2}/\d{1,2}/\d{2,4})\s+'
            r'(?P<desc>\d+\s*YD\s+[\d/]+\s*/?\s*(?:WEEK|WK|MONTH))\s+'
            r'(?:\d{1,2}/\d{1,2}\s*[-\u2013]\s*\d{1,2}/\d{1,2})\s*\n?'
            r'\$(?P<amount>[\d,]+\.?\d*)'
        ),
        'regex_flags': 'IGNORECASE',
        'capture_group': 0,
        'normalization': 'NONE',
        'scan_type': 'INLINE',
        'scan_lines': 1,
        'date_format': None,
        'is_no_account': False,
        'execution_mode': 'MULTI',
        'capture_map': json.dumps({'desc': 'charge_description', 'amount': 'amount'}),
        'pattern_tier': 'TIER_1',
        'activation_condition': 'trashbilling',
        'description_template': None,
        'notes': 'WM TrashBilling subsidiary format. charge_code_engine.py tb_pat.',
    },
    {
        'vendor_name': 'Waste Management',
        'field': 'charge_line_item',
        'format_variant': 1,
        'pattern_type': 'PRIMARY',
        'priority': 10,
        'regex_pattern': (
            r'(?P<date>\d{1,2}/\d{1,2}/\d{4})\s+'
            r'(?:[A-Z]{0,4}\d{5,}\s+)?'
            r'(?:Trash|Cardboard|Recycl\w*|MSW|OCC|Organics?|'
            r'Single|Food|Green\w*|Metal|Mixed|Wood|'
            r'Construc\w*|Co-?\w*)\s+'
            r'(?:[^\d\s]\S*\s+)?'
            r'(?P<qty>\d+\.?\d*)\s+'
            r'(?P<desc>.+?)\s+'
            r'(?P<price>-?\d[\d,]*\.\d{2})\.?\s+'
            r'(?P<tax>\d[\d,]*\.\d{2})\.?\s+'
            r'(?P<amount>-?\d[\d,]*\.\d{2})\.?\s*$'
        ),
        'regex_flags': 'IGNORECASE|MULTILINE',
        'capture_group': 0,
        'normalization': 'NONE',
        'scan_type': 'INLINE',
        'scan_lines': 1,
        'date_format': None,
        'is_no_account': False,
        'execution_mode': 'MULTI',
        'capture_map': json.dumps({'desc': 'charge_description', 'qty': 'qty',
                                    'price': 'unit_price', 'amount': 'amount'}),
        'pattern_tier': 'TIER_1',
        'activation_condition': None,
        'description_template': None,
        'notes': 'WM NG full inline format (date+material+qty+desc+price+tax+amount). charge_code_engine.py ng_wm_pat.',
    },
    {
        'vendor_name': 'Waste Management',
        'field': 'charge_line_item',
        'format_variant': 1,
        'pattern_type': 'PRIMARY',
        'priority': 15,
        'regex_pattern': (
            r'(?P<date>\d{1,2}/\d{1,2}/\d{4})\s+'
            r'(?:[A-Z]{0,4}\d{5,}\s+)?'
            r'(?:Trash|Cardboard|Recycl\w*|MSW|OCC|Organics?|'
            r'Single|Food|Green\w*|Metal|Mixed|Wood|'
            r'Construc\w*|Co-?\w*)\s+'
            r'(?:[^\d\s]\S*\s+)?'
            r'(?P<qty>\d+\.?\d*)\s+'
            r'(?P<desc>.+?)\s+'
            r'(?P<price>-?\d[\d,]*\.\d{2})\.?\s+'
            r'(?P<amount>\d[\d,]*\.\d{2})\.?\s*$'
        ),
        'regex_flags': 'IGNORECASE|MULTILINE',
        'capture_group': 0,
        'normalization': 'NONE',
        'scan_type': 'INLINE',
        'scan_lines': 1,
        'date_format': None,
        'is_no_account': False,
        'execution_mode': 'MULTI',
        'capture_map': json.dumps({'desc': 'charge_description', 'qty': 'qty',
                                    'price': 'unit_price', 'amount': 'amount'}),
        'pattern_tier': 'TIER_1',
        'activation_condition': None,
        'description_template': None,
        'notes': 'WM NG truncated format (no tax column). charge_code_engine.py ng_wm_trunc.',
    },
    {
        'vendor_name': 'Waste Management',
        'field': 'charge_line_item',
        'format_variant': 1,
        'pattern_type': 'PRIMARY',
        'priority': 20,
        'regex_pattern': (
            r'(?P<date>\d{1,2}/\d{1,2}/\d{4})\s*'
            r'(?:[\w\d]+\s+)?'
            r'(?P<material>Trash|Cardboard|Recycl\w*|MSW|OCC|Organics?|'
            r'Single\s*\n?\s*Stream\s*\n?\s*Recycl\w*|Food\s*\n?\s*Waste)\s+'
            r'(?P<qty>[\d.]+)\s+(?P<price>[\d,.]+)\s+(?P<tax>[\d,.]+)\s+'
            r'(?P<amount>-?[\d,.]+)\s*\n'
            r'(?P<desc>(?:Pickup|Container|Delivery|Haul|Disposal|Excess|Removal|'
            r'Government|Utility|Fuel|Landfill)[^\n]+)'
        ),
        'regex_flags': 'IGNORECASE',
        'capture_group': 0,
        'normalization': 'NONE',
        'scan_type': 'INLINE',
        'scan_lines': 1,
        'date_format': None,
        'is_no_account': False,
        'execution_mode': 'MULTI',
        'capture_map': json.dumps({'desc': 'charge_description', 'qty': 'qty',
                                    'price': 'unit_price', 'amount': 'amount'}),
        'pattern_tier': 'TIER_1',
        'activation_condition': None,
        'description_template': None,
        'notes': 'WM standard 2-line format (material+nums on line 1, desc on line 2). charge_code_engine.py wm_pat.',
    },
    {
        'vendor_name': 'Waste Management',
        'field': 'charge_line_item',
        'format_variant': 1,
        'pattern_type': 'PRIMARY',
        'priority': 30,
        'regex_pattern': (
            r'(?P<date>\d{1,2}/\d{1,2}/\d{4})\s*'
            r'(?P<material>\w+(?:\s+\w+)?)\s+'
            r'0\.00\s+0\.00\s+[\d.]+\s+'
            r'(?P<amount>-?[\d,.]+)\s*\n'
            r'(?P<desc>(?:Utility\s+Tax|Pickup\s+Increase|Container\s+Service\s+Charge|'
            r'Disposal\s+Increase|Fuel\s+Surcharge)[^\n]+)'
        ),
        'regex_flags': 'IGNORECASE',
        'capture_group': 0,
        'normalization': 'NONE',
        'scan_type': 'INLINE',
        'scan_lines': 1,
        'date_format': None,
        'is_no_account': False,
        'execution_mode': 'MULTI',
        'capture_map': json.dumps({'desc': 'charge_description', 'amount': 'amount'}),
        'pattern_tier': 'TIER_2',
        'activation_condition': None,
        'description_template': None,
        'notes': 'WM tax/fee lines (qty=0.00). charge_code_engine.py tax_pat.',
    },
    {
        'vendor_name': 'Waste Management',
        'field': 'charge_line_item',
        'format_variant': 1,
        'pattern_type': 'PRIMARY',
        'priority': 35,
        'regex_pattern': (
            r'(?P<date>\d{1,2}/\d{1,2}/\d{4})\s*'
            r'(?P<material>\w+(?:\s+\w+)?)\s+'
            r'[\d.]+\s+[\d,.]+\s+[\d,.]+\s+'
            r'-(?P<amount>[\d,.]+)\s*\n'
            r'(?P<desc>[^\n]+)'
        ),
        'regex_flags': 'IGNORECASE',
        'capture_group': 0,
        'normalization': 'NONE',
        'scan_type': 'INLINE',
        'scan_lines': 1,
        'date_format': None,
        'is_no_account': False,
        'execution_mode': 'MULTI',
        'capture_map': json.dumps({'desc': 'charge_description', 'amount': 'amount'}),
        'pattern_tier': 'TIER_2',
        'activation_condition': None,
        'description_template': None,
        'notes': 'WM credit lines (negative amount). charge_code_engine.py credit_pat.',
    },
    {
        'vendor_name': 'Waste Management',
        'field': 'charge_line_item',
        'format_variant': 1,
        'pattern_type': 'FALLBACK',
        'priority': 80,
        'regex_pattern': r'(?P<location>[\w\s\-]+)\s+LOCATION\s+CHARGES\s+(?P<amount>[\d,.]+)',
        'regex_flags': 'IGNORECASE',
        'capture_group': 0,
        'normalization': 'NONE',
        'scan_type': 'INLINE',
        'scan_lines': 1,
        'date_format': None,
        'is_no_account': False,
        'execution_mode': 'MULTI',
        'capture_map': json.dumps({'location': 'charge_description', 'amount': 'amount'}),
        'pattern_tier': 'TIER_FALLBACK',
        'activation_condition': None,
        'description_template': None,
        'notes': 'WM location charges fallback. charge_code_engine.py loc_pat.',
    },
    {
        'vendor_name': 'Waste Management',
        'field': 'charge_line_item',
        'format_variant': 1,
        'pattern_type': 'FALLBACK',
        'priority': 90,
        'regex_pattern': r'Current\s+Invoice\s+Charges\s*\n?\$?\s*(?P<amt>[\d,]+\.?\d*)',
        'regex_flags': 'IGNORECASE',
        'capture_group': 0,
        'normalization': 'NONE',
        'scan_type': 'INLINE',
        'scan_lines': 1,
        'date_format': None,
        'is_no_account': False,
        'execution_mode': 'MULTI',
        'capture_map': json.dumps({'amt': 'amount'}),
        'pattern_tier': 'TIER_FALLBACK',
        'activation_condition': None,
        'description_template': None,
        'notes': 'WM current invoice total fallback. Only fires if no TIER_1/TIER_2 matched.',
    },

    # --- GFL (9 patterns) ---
    {
        'vendor_name': 'GFL',
        'field': 'charge_line_item',
        'format_variant': 1,
        'pattern_type': 'PRIMARY',
        'priority': 10,
        'regex_pattern': (
            r'(?P<date>\d{1,2}[-/]\d{1,2}[-/]\d{2,4})\s+'
            r'(?P<desc>(?:\d+\s*(?:CY|GAL|YD)\s+)?'
            r'(?:ROLL\s*OFF|FRONT\s*LOAD|RESIDENTIAL|COMMERCIAL)?\s*'
            r'(?:HAUL|SVC|SERVICE|MSW|TRASH|RECYC\w*)?[\w\s]*?)'
            r'(?:WO#\d+\s*)?(?:po\s*)?'
            r'(?P<qty>[\d.]+)\s*[Xx]?\s*\$?(?P<rate>[\d,.]+)\s+'
            r'\$(?P<amount>[\d,.]+)'
        ),
        'regex_flags': 'IGNORECASE',
        'capture_group': 0,
        'normalization': 'NONE',
        'scan_type': 'INLINE',
        'scan_lines': 1,
        'date_format': None,
        'is_no_account': False,
        'execution_mode': 'MULTI',
        'capture_map': json.dumps({'desc': 'charge_description', 'qty': 'qty',
                                    'rate': 'unit_price', 'amount': 'amount'}),
        'pattern_tier': 'TIER_1',
        'activation_condition': None,
        'description_template': None,
        'notes': 'GFL QTY x RATE format. configured.py qty_x_pattern. Requires $ on amount.',
    },
    {
        'vendor_name': 'GFL',
        'field': 'charge_line_item',
        'format_variant': 1,
        'pattern_type': 'PRIMARY',
        'priority': 15,
        'regex_pattern': (
            r'Serv\s*#\s*(?P<num>\d+)\s+(?P<desc>COMM\s+(?:FL|RL|RO)\s+[\w\s]+\d+YD)\s*\n'
            r'(?P<date>\d{1,2}/\d{1,2}/\d{2,4})\s*\n?'
            r'(?P<service>[\w\s]+SERVICE)?\s*\n?'
            r'(?:[\w\s]+\d{1,2}/\d{2,4}\s*[-\u2013]\s*[\w\s]+\d{1,2}/\d{2,4}\s*\n?)?'
            r'\$(?P<rate>[\d,]+\.?\d*)\s*\n?'
            r'(?P<qty>[\d.]+)\s*\n?'
            r'\$(?P<amount>[\d,]+\.?\d*)'
        ),
        'regex_flags': 'IGNORECASE',
        'capture_group': 0,
        'normalization': 'NONE',
        'scan_type': 'INLINE',
        'scan_lines': 1,
        'date_format': None,
        'is_no_account': False,
        'execution_mode': 'MULTI',
        'capture_map': json.dumps({'desc': 'charge_description', 'rate': 'unit_price',
                                    'qty': 'qty', 'amount': 'amount'}),
        'pattern_tier': 'TIER_1',
        'activation_condition': None,
        'description_template': None,
        'notes': 'GFL Serv # block format. configured.py serv_pattern.',
    },
    {
        'vendor_name': 'GFL',
        'field': 'charge_line_item',
        'format_variant': 1,
        'pattern_type': 'PRIMARY',
        'priority': 18,
        'regex_pattern': (
            r'(?:MANUAL\s+BILLING|Manual\s+Bill)\s*\n?'
            r'(?:[\w\s]+\n)*?'
            r'(?P<date>\d{1,2}/\d{1,2}/\d{2,4})\s*\n?'
            r'(?:\d+\s*\n)?'
            r'(?P<qty>[\d.]+)\s*\n?'
            r'\$(?P<amount>[\d,]+\.?\d*)'
        ),
        'regex_flags': 'IGNORECASE',
        'capture_group': 0,
        'normalization': 'NONE',
        'scan_type': 'INLINE',
        'scan_lines': 1,
        'date_format': None,
        'is_no_account': False,
        'execution_mode': 'MULTI',
        'capture_map': json.dumps({'qty': 'qty', 'amount': 'amount'}),
        'pattern_tier': 'TIER_1',
        'activation_condition': None,
        'description_template': 'Manual Billing',
        'notes': 'GFL Manual Billing format. configured.py manual_pattern.',
    },
    {
        'vendor_name': 'GFL',
        'field': 'charge_line_item',
        'format_variant': 1,
        'pattern_type': 'PRIMARY',
        'priority': 20,
        'regex_pattern': (
            r'(?P<date>\d{1,2}/\d{1,2}/\d{2,4})\s+'
            r'(?P<desc>COMM\s+(?:FL|RL|RO)\s+[\w\s]+\d+YD)\s*\n?'
            r'(?:TRASH|RECYCLING|ORGANICS)?\s*(?:STANDARD\s+)?SERVICE\s*\n?'
            r'(?:[\w\s]+\d{1,2}/\d{2,4}\s*[-\u2013]\s*[\w\s]+\d{1,2}/\d{2,4}\s*\n?)?'
            r'\$(?P<rate>[\d,]+\.?\d*)\s+'
            r'(?P<qty>[\d.]+)\s+'
            r'\$(?P<amount>[\d,]+\.?\d*)'
        ),
        'regex_flags': 'IGNORECASE',
        'capture_group': 0,
        'normalization': 'NONE',
        'scan_type': 'INLINE',
        'scan_lines': 1,
        'date_format': None,
        'is_no_account': False,
        'execution_mode': 'MULTI',
        'capture_map': json.dumps({'desc': 'charge_description', 'rate': 'unit_price',
                                    'qty': 'qty', 'amount': 'amount'}),
        'pattern_tier': 'TIER_1',
        'activation_condition': None,
        'description_template': None,
        'notes': 'GFL inline DATE DESC RATE QTY AMOUNT. configured.py inline_pattern.',
    },
    {
        'vendor_name': 'GFL',
        'field': 'charge_line_item',
        'format_variant': 1,
        'pattern_type': 'PRIMARY',
        'priority': 25,
        'regex_pattern': (
            r'(?P<date>\d{1,2}[-/]\d{1,2}[-/]\d{2,4})\s+'
            r'(?P<desc>\d+\s*GAL\s+(?:RESIDENTIAL|COMMERCIAL)\s+SVC\s*[\w.]*)\s*\n?'
            r'(?:[\d.]+\s*\n)?'
            r'\$(?P<amount>[\d,.]+)'
        ),
        'regex_flags': 'IGNORECASE',
        'capture_group': 0,
        'normalization': 'NONE',
        'scan_type': 'INLINE',
        'scan_lines': 1,
        'date_format': None,
        'is_no_account': False,
        'execution_mode': 'MULTI',
        'capture_map': json.dumps({'desc': 'charge_description', 'amount': 'amount'}),
        'pattern_tier': 'TIER_1',
        'activation_condition': None,
        'description_template': None,
        'notes': 'GFL GAL RESIDENTIAL SVC format. configured.py gal_pattern.',
    },
    {
        'vendor_name': 'GFL',
        'field': 'charge_line_item',
        'format_variant': 1,
        'pattern_type': 'PRIMARY',
        'priority': 30,
        'regex_pattern': (
            r'(?P<date>\d{1,2}[-/]\d{1,2}[-/]\d{2,4})\s+'
            r'(?P<desc>\d+\s*CY\s+(?:FRONT\s+LOAD|ROLL\s*OFF)\s+SVC\s+[\w\s]+?)'
            r'(?P<qty>[\d.]+)\s*'
            r'(?:\$(?P<rate>[\d,]+\.?\d*)\s+)?'
            r'\$(?P<amount>[\d,]+\.?\d*)'
        ),
        'regex_flags': 'IGNORECASE',
        'capture_group': 0,
        'normalization': 'NONE',
        'scan_type': 'INLINE',
        'scan_lines': 1,
        'date_format': None,
        'is_no_account': False,
        'execution_mode': 'MULTI',
        'capture_map': json.dumps({'desc': 'charge_description', 'qty': 'qty',
                                    'rate': 'unit_price', 'amount': 'amount'}),
        'pattern_tier': 'TIER_1',
        'activation_condition': None,
        'description_template': None,
        'notes': 'GFL CY FRONT LOAD/ROLL OFF format. configured.py cy_pattern.',
    },
    {
        'vendor_name': 'GFL',
        'field': 'charge_line_item',
        'format_variant': 1,
        'pattern_type': 'PRIMARY',
        'priority': 40,
        'regex_pattern': (
            r'(?P<date>\d{1,2}[-/]\d{1,2}[-/]\d{2,4})?\s*'
            r'(?P<desc>Fuel\s+Surcharge)\s*\n?'
            r'\$(?P<amount>[\d,]+\.?\d*)'
        ),
        'regex_flags': 'IGNORECASE',
        'capture_group': 0,
        'normalization': 'NONE',
        'scan_type': 'INLINE',
        'scan_lines': 1,
        'date_format': None,
        'is_no_account': False,
        'execution_mode': 'MULTI',
        'capture_map': json.dumps({'desc': 'charge_description', 'amount': 'amount'}),
        'pattern_tier': 'TIER_2',
        'activation_condition': None,
        'description_template': None,
        'notes': 'GFL fuel surcharge. configured.py fuel_pattern.',
    },
    {
        'vendor_name': 'GFL',
        'field': 'charge_line_item',
        'format_variant': 1,
        'pattern_type': 'PRIMARY',
        'priority': 45,
        'regex_pattern': (
            r'(?P<desc>LOCK\s+FEE|ADMIN\s+FEE|ENVIRONMENTAL\s+FEE|OVERAGE|'
            r'ROLL\s*OFF\s+TRIP\s+CHARGE|DISPOSAL\s+AND\s+RELATED\s+FEES)\s*'
            r'(?:WO#\d+\s*)?(?:po\s*)?'
            r'(?:[\w\s]+\d{1,2}/\d{2,4}\s*[-\u2013]\s*[\w\s]+\d{1,2}/\d{2,4}\s*\n?)?'
            r'(?:\$(?P<rate>[\d,]+\.?\d*)\s+)?'
            r'(?P<qty>[\d.]+)?\s*'
            r'\$(?P<amount>[\d,]+\.?\d*)'
        ),
        'regex_flags': 'IGNORECASE',
        'capture_group': 0,
        'normalization': 'NONE',
        'scan_type': 'INLINE',
        'scan_lines': 1,
        'date_format': None,
        'is_no_account': False,
        'execution_mode': 'MULTI',
        'capture_map': json.dumps({'desc': 'charge_description', 'rate': 'unit_price',
                                    'qty': 'qty', 'amount': 'amount'}),
        'pattern_tier': 'TIER_2',
        'activation_condition': None,
        'description_template': None,
        'notes': 'GFL lock/admin/environmental fee lines. configured.py fee_pattern. Requires $ on amount.',
    },
    {
        'vendor_name': 'GFL',
        'field': 'charge_line_item',
        'format_variant': 1,
        'pattern_type': 'FALLBACK',
        'priority': 90,
        'regex_pattern': r'(?:SITE\s+(?:TOTAL|Sub\s+Total)|Site\s+Total)\s*:?\s*\n?\$\s*(?P<amount>[\d,]+\.?\d*)',
        'regex_flags': 'IGNORECASE',
        'capture_group': 0,
        'normalization': 'NONE',
        'scan_type': 'INLINE',
        'scan_lines': 1,
        'date_format': None,
        'is_no_account': False,
        'execution_mode': 'MULTI',
        'capture_map': json.dumps({'amount': 'amount'}),
        'pattern_tier': 'TIER_FALLBACK',
        'activation_condition': None,
        'description_template': None,
        'notes': 'GFL site total fallback. configured.py site_total_pattern.',
    },

    # --- Anytime Waste (5 patterns) ---
    {
        'vendor_name': 'Anytime Waste',
        'field': 'charge_line_item',
        'format_variant': 1,
        'pattern_type': 'PRIMARY',
        'priority': 10,
        'regex_pattern': (
            r'(?P<daterange>\d{1,2}/\d{1,2}/\d{2,4}\s*[-\u2013]\s*\d{1,2}/\d{1,2}/\d{2,4})\s+'
            r'(?P<desc>[\w\s\-]+(?:Trash|Recycl\w*|Cardboard|OCC|RENT|FL)?[\w\s]*?)'
            r'\$\s*(?P<rate>[\d,]+\.?\d*)\s+per\s+\w+\s*\n?[\d.]*\s*\n?'
            r'(?P<amount>[\d,]+\.?\d*)'
        ),
        'regex_flags': 'IGNORECASE',
        'capture_group': 0,
        'normalization': 'NONE',
        'scan_type': 'INLINE',
        'scan_lines': 1,
        'date_format': None,
        'is_no_account': False,
        'execution_mode': 'MULTI',
        'capture_map': json.dumps({'desc': 'charge_description', 'rate': 'unit_price',
                                    'amount': 'amount'}),
        'pattern_tier': 'TIER_1',
        'activation_condition': None,
        'description_template': None,
        'notes': 'Anytime Waste inline date-range format. configured.py inline_pattern.',
    },
    {
        'vendor_name': 'Anytime Waste',
        'field': 'charge_line_item',
        'format_variant': 1,
        'pattern_type': 'PRIMARY',
        'priority': 15,
        'regex_pattern': (
            r'(?P<desc>(?:Disposal|Haul)\s+Fees?\s+(?:Trash|Cardboard|Recycl\w*|OCC|MSW|Metal)|'
            r'Switch\s+Out\s+\d+\s*(?:YD|yd)?\s*(?:Roll\s*Off)?|'
            r'No\s+Return\s+\d+\s*(?:YD|yd)?\s*(?:Roll\s*Off)?|'
            r'\d+\s*(?:yd|YD)\s*(?:Flat|Slant)?\s*[-\u2013]?\s*'
            r'(?:Front\s*Load|Roll\s*Off)?\s*(?:Trash|Recycl\w*|Cardboard)?|'
            r'Monthly\s+Rent|'
            r'\d+\s*YD\s+OT\s+MONTHLY\s+RENT)\s*\n?'
            r'(?P<amount>[\d,]+\.?\d*)'
        ),
        'regex_flags': 'IGNORECASE',
        'capture_group': 0,
        'normalization': 'NONE',
        'scan_type': 'INLINE',
        'scan_lines': 1,
        'date_format': None,
        'is_no_account': False,
        'execution_mode': 'MULTI',
        'capture_map': json.dumps({'desc': 'charge_description', 'amount': 'amount'}),
        'pattern_tier': 'TIER_1',
        'activation_condition': None,
        'description_template': None,
        'notes': 'Anytime Waste site-section desc+amount. configured.py desc_keywords.',
    },
    {
        'vendor_name': 'Anytime Waste',
        'field': 'charge_line_item',
        'format_variant': 1,
        'pattern_type': 'PRIMARY',
        'priority': 16,
        'regex_pattern': (
            r'TOTAL\s*\n\s*(?P<amount>[\d,]+\.\d{2})'
        ),
        'regex_flags': 'IGNORECASE',
        'capture_group': 0,
        'normalization': 'NONE',
        'scan_type': 'INLINE',
        'scan_lines': 1,
        'date_format': None,
        'is_no_account': False,
        'execution_mode': 'MULTI',
        'capture_map': json.dumps({'amount': 'amount'}),
        'pattern_tier': 'TIER_1',
        'activation_condition': None,
        'description_template': 'Site Total',
        'notes': 'Anytime Waste TOTAL column amount extraction. configured.py total_section.',
    },
    {
        'vendor_name': 'Anytime Waste',
        'field': 'charge_line_item',
        'format_variant': 1,
        'pattern_type': 'PRIMARY',
        'priority': 30,
        'regex_pattern': (
            r'(?P<desc>(?:Fuel|Energy|Environmental|Admin|Regulatory|'
            r'Recovery|Sustainability)\s*(?:Surcharge|Fee|Charge))\s*\n?'
            r'\$?(?P<amount>[\d,]+\.?\d*)'
        ),
        'regex_flags': 'IGNORECASE',
        'capture_group': 0,
        'normalization': 'NONE',
        'scan_type': 'INLINE',
        'scan_lines': 1,
        'date_format': None,
        'is_no_account': False,
        'execution_mode': 'MULTI',
        'capture_map': json.dumps({'desc': 'charge_description', 'amount': 'amount'}),
        'pattern_tier': 'TIER_2',
        'activation_condition': None,
        'description_template': None,
        'notes': 'Anytime Waste surcharge/fee lines.',
    },
    {
        'vendor_name': 'Anytime Waste',
        'field': 'charge_line_item',
        'format_variant': 1,
        'pattern_type': 'FALLBACK',
        'priority': 90,
        'regex_pattern': r'AMOUNT\s*\n\s*(?P<amt>[\d,]+\.?\d*)',
        'regex_flags': 'IGNORECASE',
        'capture_group': 0,
        'normalization': 'NONE',
        'scan_type': 'INLINE',
        'scan_lines': 1,
        'date_format': None,
        'is_no_account': False,
        'execution_mode': 'MULTI',
        'capture_map': json.dumps({'amt': 'amount'}),
        'pattern_tier': 'TIER_FALLBACK',
        'activation_condition': None,
        'description_template': None,
        'notes': 'Anytime Waste invoice total fallback. Only fires if no TIER_1/TIER_2 matched.',
    },

]


# ---------------------------------------------------------------------------
# Loader
# ---------------------------------------------------------------------------

_INSERT_SQL = """
    INSERT INTO ip_vendor_pattern (
        vendor_name, field, format_variant, pattern_type, priority,
        regex_pattern, regex_flags, capture_group, normalization,
        scan_type, scan_lines, date_format, is_no_account, notes,
        deployed_by,
        execution_mode, capture_map, pattern_tier,
        activation_condition, description_template
    ) VALUES %s
"""

_TEMPLATE = (
    "("
    "%(vendor_name)s, %(field)s, %(format_variant)s, %(pattern_type)s, %(priority)s, "
    "%(regex_pattern)s, %(regex_flags)s, %(capture_group)s, %(normalization)s, "
    "%(scan_type)s, %(scan_lines)s, %(date_format)s, %(is_no_account)s, %(notes)s, "
    "%(deployed_by)s, "
    "%(execution_mode)s, %(capture_map)s, %(pattern_tier)s, "
    "%(activation_condition)s, %(description_template)s"
    ")"
)


def _validate_patterns(patterns: list[dict]) -> list[str]:
    """Compile each regex and return list of error messages (empty = OK)."""
    errors = []
    for i, p in enumerate(patterns):
        regex = p['regex_pattern']
        flags_str = p.get('regex_flags', 'NONE')

        # Build flags
        flags = 0
        if flags_str and flags_str != 'NONE':
            for part in flags_str.split('|'):
                part = part.strip()
                if hasattr(re, part):
                    flags |= getattr(re, part)
                else:
                    errors.append(f"Pattern {i} ({p['vendor_name']}/{p['field']}): unknown flag '{part}'")

        try:
            re.compile(regex, flags)
        except re.error as exc:
            errors.append(f"Pattern {i} ({p['vendor_name']}/{p['field']}): regex error: {exc}")

    return errors


def load_patterns(dry_run: bool = False) -> int:
    """Delete existing patterns and insert all VENDOR_PATTERNS rows.

    Returns the number of rows inserted.
    """
    # Validate first
    errors = _validate_patterns(VENDOR_PATTERNS)
    if errors:
        for e in errors:
            log.error(e)
        raise ValueError(f"{len(errors)} pattern validation error(s)")

    log.info("Validated %d patterns (all regex compile OK)", len(VENDOR_PATTERNS))

    if dry_run:
        # Print summary
        from collections import Counter
        by_vendor_field = Counter((p['vendor_name'], p['field']) for p in VENDOR_PATTERNS)
        print(f"\n  {len(VENDOR_PATTERNS)} patterns validated (dry run)")
        for (v, f), count in sorted(by_vendor_field.items()):
            print(f"    {v:25s} {f:20s} {count}")
        return len(VENDOR_PATTERNS)

    # Prepare rows with deployed_by + defaults for new columns
    rows = []
    for p in VENDOR_PATTERNS:
        row = dict(p)
        row['deployed_by'] = 'load_vendor_patterns.py'
        row.setdefault('execution_mode', 'SINGLE')
        row.setdefault('capture_map', None)
        row.setdefault('pattern_tier', 'TIER_1')
        row.setdefault('activation_condition', None)
        row.setdefault('description_template', None)
        # Serialize capture_map dict to JSON string for psycopg2
        if isinstance(row.get('capture_map'), dict):
            import json as _json
            row['capture_map'] = _json.dumps(row['capture_map'])
        rows.append(row)

    with get_cursor() as cur:
        # Clear FK references before deleting patterns
        cur.execute("UPDATE ip_extraction_result SET vendor_pattern_id = NULL WHERE vendor_pattern_id IS NOT NULL")
        nulled = cur.rowcount
        if nulled:
            log.info("Cleared %d FK references in ip_extraction_result", nulled)
        cur.execute("UPDATE ip_fix_log SET vendor_pattern_id = NULL WHERE vendor_pattern_id IS NOT NULL")

        # Truncate existing patterns (idempotent reload)
        cur.execute("DELETE FROM ip_vendor_pattern")
        deleted = cur.rowcount
        if deleted:
            log.info("Deleted %d existing pattern rows", deleted)

        # Batch insert
        psycopg2.extras.execute_values(
            cur,
            _INSERT_SQL,
            rows,
            template=_TEMPLATE,
            page_size=100,
        )
        cur.connection.commit()

    log.info("Inserted %d pattern rows", len(rows))
    return len(rows)
