# Account Extraction Module - Claude Instructions

## Purpose

This document provides all context needed for Claude to efficiently update account extraction patterns. Load this document whenever you need to add new vendors, fix extraction failures, or improve extraction rates.

---

## Module Overview

**File:** `/mnt/project/account_extraction_engine_v3.py`  
**Function:** Extract customer account numbers from invoice OCR text based on detected vendor  
**Current Performance:** 92.5% average extraction rate (varies by vendor)  
**Configured Vendors:** 114 (98 with account numbers, 16 invoice-based)

---

## Data Files Reference

| File | Purpose | Key Columns |
|------|---------|-------------|
| `ocr_chunk_*.csv` (1-7) | Raw OCR text from invoices | `md5_hash`, `source_file`, `raw_text` |
| `vendor_results.csv` | Vendor detection results | `md5_hash`, `detected_vendor` |
| `services_chunk_*.csv` (1-2) | Service records for validation | `vendor_name`, `site_reference` (often contains account) |
| `billing_chunk_*.csv` (1-6) | Billing records | `billing_reference` (hauler invoice ID) |
| `account_review_interface.xlsx` | Review/management interface | Extraction rates, sample failures |

---

## Critical Architecture Rules

### 1. Vendor-First Dispatch

Account extraction is **routed by vendor name**. The detected vendor determines which extraction function runs:

```python
# Correct workflow:
vendor = detect_vendor(ocr_text)           # Step 1: Detect vendor
account = extract_account(vendor, ocr_text) # Step 2: Extract account with vendor-specific logic
```

### 2. Deterministic Extraction

The extraction engine follows strict rules:
- Returns **exact match** or **None** (no guessing)
- Each vendor has explicit extraction logic
- If pattern doesn't match exactly, extraction fails cleanly

### 3. Module Structure

```python
VENDOR_ACCOUNTS = {
    'Vendor Name': {
        'has_account': True/False,
        'format': 'Description of format',
        'examples': ['123456', '789012'],
        'extract': _extract_vendor_function
    }
}

def extract_account(vendor_name, text):
    if vendor_name not in VENDOR_ACCOUNTS:
        return None
    config = VENDOR_ACCOUNTS[vendor_name]
    if not config['has_account']:
        return None
    return config['extract'](text)
```

---

## Extraction Function Pattern

Every vendor extraction function follows this structure:

```python
def _extract_vendor_name(text: str) -> Optional[str]:
    """
    Format: Description of account format
    Examples: ABC123, XYZ789
    """
    lines = text.split('\\n')  # Note: literal backslash-n from OCR
    
    # Format 1: Primary pattern
    match = re.search(r'pattern', text)
    if match:
        return match.group(1)
    
    # Format 2: Header/value pattern
    for i, line in enumerate(lines):
        if 'ACCOUNT' in line.upper():
            for j in range(i+1, min(i+5, len(lines))):
                val = lines[j].strip()
                if re.match(r'^\d{6}$', val):
                    return val
    
    return None

VENDOR_ACCOUNTS['Vendor Name'] = {
    'has_account': True,
    'format': 'NNNNNN',
    'examples': ['123456', '789012'],
    'extract': _extract_vendor_name
}
```

---

## Common OCR Patterns

### Pattern 1: Inline Label + Value

```
Customer No.: 123456
Account #: ABC789
```

**Extraction:**
```python
match = re.search(r'Customer\s*No\.?:?\s*(\d{6})', text, re.I)
```

### Pattern 2: Header Then Value (Next Line)

```
ACCOUNT #
123456
```

**Extraction:**
```python
lines = text.split('\\n')
for i, line in enumerate(lines):
    if 'ACCOUNT #' in line.upper():
        for j in range(i+1, min(i+5, len(lines))):
            val = lines[j].strip()
            if re.match(r'^\d{6}$', val):
                return val
```

### Pattern 3: Value Before Label (OCR Column Inversion)

```
123456
CUSTOMER NO.
```

**Extraction:**
```python
for i, line in enumerate(lines):
    if 'CUSTOMER NO' in line.upper():
        for j in range(max(0, i-3), i):  # Look BEFORE
            val = lines[j].strip()
            if re.match(r'^\d{5}$', val):
                return val
```

### Pattern 4: Table Headers with Values Below

```
INVOICE NO.   |   ACCOUNT NO.   |   DATE
001234        |   567890        |   10/15/25
```

OCR often captures as:
```
INVOICE NO.
ACCOUNT NO.
DATE
001234
567890
10/15/25
```

**Extraction:**
```python
for i, line in enumerate(lines):
    if line.strip() == 'ACCOUNT NO.':
        # Values typically appear N lines after headers
        if i + 5 < len(lines):
            val = lines[i + 5].strip()
            if re.match(r'^\d{6}$', val):
                return val
```

---

## Tier-Based Vendor Organization

The module organizes vendors by invoice volume for prioritization:

| Tier | Volume | Examples |
|------|--------|----------|
| **T1** | >2,000 | Waste Connections, Republic, WM, GFL, Anytime |
| **T2** | 1,000-2,000 | Rumpke, Waste Pro, Cockey's, Universal |
| **T3** | 500-1,000 | Robinson, Hamilton, Active, Priority, Casella |
| **T4** | 200-500 | Meridian, Frontier, FCC, SmartTrash, LRS |
| **T5** | <200 | Various regional haulers |

---

## Common Issues and Fixes

### Issue 1: Extraction Fails (Returns None)

**Symptom:** Vendor detected correctly but account returns None

**Diagnosis Steps:**
1. Get sample OCR text for the failing invoice
2. Print the raw text to see exact format
3. Identify where account number appears
4. Check if pattern handles that position

**Example Fix (Lightning Disposal):**
```python
# BEFORE (0% extraction): Looking after label
for i, line in enumerate(lines):
    if 'CUSTOMER NO' in line.upper():
        for j in range(i+1, min(i+4, len(lines))):  # After only
            ...

# AFTER (100% extraction): Looking before AND after label
for i, line in enumerate(lines):
    if 'CUSTOMER NO' in line.upper():
        # Check BEFORE (OCR column inversion)
        for j in range(max(0, i-3), i):
            ...
        # Also check after
        for j in range(i+1, min(i+4, len(lines))):
            ...
```

### Issue 2: Wrong Value Extracted

**Symptom:** Extraction returns a value, but it's not the account number

**Diagnosis:** Pattern too generic, matching invoice number or other data

**Fix:** Make pattern more specific with:
- Exact digit counts: `\d{6}` instead of `\d+`
- Required prefixes: `r'(WGY[A-Z0-9]{5,8})'`
- Label proximity requirements

### Issue 3: Multiple Regional Formats

**Symptom:** Works for some invoices but fails for others from same vendor

**Example (FCC Environmental):**
```python
def _extract_fcc_environmental(text):
    # Tampa format: TS00154796
    match = re.search(r'Customer\s*ID:\s*(TS\d{8})', text, re.I)
    if match:
        return match.group(1)
    
    # Palm Beach format: PBC-3453-5
    match = re.search(r'Customer\s*ID:\s*(PBC-?\d+-?\d+)', text, re.I)
    if match:
        return match.group(1)
    
    # Houston format: ACCOUNT # with 5-6 digit
    for i, line in enumerate(lines):
        if 'ACCOUNT #' in line.upper():
            # ... extract 5-6 digit value
    
    return None
```

### Issue 4: Vendor Misdetection Contamination

**Symptom:** Account extraction works, but vendor was wrong

**Fix:** Add misdetection filters at start of extraction function:

```python
def _extract_waste_management(text):
    # Filter misdetected vendors
    misdetects = ['WIN WASTE', 'WEST CENTRAL', 'BRUIN WASTE']
    if any(x in text.upper() for x in misdetects):
        return None  # Don't extract - vendor detection was wrong
    
    # Normal extraction logic...
```

---

## Workflow: Adding a New Vendor

### Step 1: Gather Sample OCR

Get 5-10 sample invoices from the vendor:
```python
import pandas as pd

ocr = pd.read_csv('ocr_chunk_1.csv')
results = pd.read_csv('vendor_results.csv')

# Get samples for specific vendor
vendor_hashes = results[results['detected_vendor'] == 'New Vendor']['md5_hash']
samples = ocr[ocr['md5_hash'].isin(vendor_hashes)]['raw_text'].head(10)
```

### Step 2: Identify Account Format

Analyze the OCR text to find:
- What label precedes/follows the account number?
- What is the exact format? (digits, prefix, separators)
- Is it consistent across samples or are there variants?

### Step 3: Create Extraction Function

```python
def _extract_new_vendor(text: str) -> Optional[str]:
    """
    Format: [Description]
    Examples: [Real examples from samples]
    """
    # Implement extraction logic
    return None

VENDOR_ACCOUNTS['New Vendor'] = {
    'has_account': True,
    'format': 'FORMAT_DESCRIPTION',
    'examples': ['example1', 'example2'],
    'extract': _extract_new_vendor
}
```

### Step 4: Test Extraction

```python
# Test against all samples
for text in samples:
    result = _extract_new_vendor(text)
    print(f"Extracted: {result}")
```

### Step 5: Validate Against Services

Cross-check extracted accounts against services data:
```python
services = pd.read_csv('services_chunk_1.csv')
vendor_services = services[services['vendor_name'].str.contains('New Vendor', case=False)]
print(vendor_services['site_reference'].unique()[:20])  # Compare with extracted
```

---

## Vendors Without Account Numbers

Some vendors don't use customer account numbers:

```python
NO_ACCOUNT_VENDORS = [
    'Standard Waste',      # Scale tickets only
    'Redbox+',             # Invoice-based
    'CRI Curbside',        # Invoice-based
    'Rocky Ridge',         # Invoice-based
    'Specific Waste',      # Manifests/certificates
    'Boyas Recycling',     # Invoice-based
    'Las Vegas Recycling', # Job numbers (not accounts)
    'Trash Taxi',          # TrashBilling ID system
    'ACES Disposal',       # TrashBilling ID
]
```

For these vendors:
```python
VENDOR_ACCOUNTS['Vendor Name'] = {
    'has_account': False,
    'format': None,
    'examples': [],
    'extract': lambda x: None,
    'notes': 'Invoice-based identification only'
}
```

---

## Performance Tracking (Color Codes)

| Color | Rate | Action |
|-------|------|--------|
| 🟢 Green | 95%+ | Maintained |
| 🟡 Yellow | 80-94% | Priority improvement |
| 🔴 Red | <80% | Critical fix needed |

**V3 Improvements (Yellow → Green):**
- Anytime Waste: 91.4% → 99.0%
- Universal Waste: 88.6% → 99.4%
- Robinson Waste: 84.4% → 96.0%
- Casella: 84.4% → 95.7%
- Meridian Waste: 88.1% → 99.4%
- Coastal Waste: 84.2% → 95.5%

---

## Quick Reference: Account Formats

| Vendor | Format | Example |
|--------|--------|---------|
| Waste Connections | DDDD-NNNNNN | 3067-261791 |
| Republic Services | D-DDDD-DDDDDDD | 3-0509-0312663 |
| Waste Management | WGYXXXXXXXX | WGY17110UB |
| GFL | XX######(#) | UK829605 |
| Rumpke | NNNNNNNNNN | 4002536510 |
| Anytime Waste | NNNNN | 24234 |
| Casella | NN-NNNNN N | 81-39019 6 |
| FCC Environmental | TS######## | TS00154796 |

---

## Testing Commands

```python
# Test single extraction
from account_extraction_engine_v3 import extract_account
result = extract_account('Waste Connections', ocr_text)
print(f"Extracted: {result}")

# Get vendor format info
from account_extraction_engine_v3 import get_account_format
fmt = get_account_format('Republic Services')
print(f"Format: {fmt['format']}, Examples: {fmt['examples']}")

# Get all configured vendors
from account_extraction_engine_v3 import get_configured_vendors
vendors = get_configured_vendors()
print(f"Configured: {len(vendors)} vendors")
```

---

## Related Modules

| Module | Dependency |
|--------|------------|
| `vendor_detection_module_v7.py` | Provides `vendor_name` input |
| `03_line_items_equipment_material` | Uses account for context |
| `04_line_items_charge_description` | Uses account for matching |

**Important:** Incorrect vendor detection cascades to wrong extraction function. Always verify vendor detection first when debugging extraction failures.

---

## Version History

| Version | Key Changes |
|---------|-------------|
| v3 | Yellow tier fixes, regional formats, misdetect filters |
| v2 | Refactored to pattern-based architecture |
| v1 | Initial implementation |

---

## Contact & Ownership

**Owner:** Shane @ Wasteology
**Module:** Invoice Processing System - Account Extraction
**Last Updated:** January 2026
