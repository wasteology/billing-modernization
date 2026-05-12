# 02 Account Extraction Module

## Overview

The Account Extraction Module is the second stage of Wasteology's invoice processing pipeline. After identifying which vendor issued an invoice, this module extracts the customer account number using vendor-specific patterns. This account number is the primary key for matching invoices to service records.

---

# Business Documentation

## What It Does

Each waste management vendor assigns customers a unique account number. When we receive an invoice, we need to extract this account number to match it against our service records database.

**Example:**
```
Vendor: Waste Connections
Invoice Text: "Account: 3067-261791..."
Extracted Account: "3067-261791"
```

## Why It Matters

1. **Service Matching:** The account number links invoices to specific service locations in our database. Without it, we can't match invoices to services.

2. **Billing Reconciliation:** We validate that charges on invoices match contracted rates. The account number identifies which contract applies.

3. **Client Reporting:** Customers expect accurate account attribution. Wrong accounts = wrong billing.

## Current Performance

| Metric | Value |
|--------|-------|
| **Configured Vendors** | 164 |
| **With Account Numbers** | 140 |
| **Invoice-Based Only** | 24 |
| **Average Extraction Rate** | 95.9% |

## Account Format Examples

Different vendors use different account number formats:

| Vendor | Format | Example |
|--------|--------|---------|
| Waste Connections | District-Account | 3067-261791 |
| Republic Services | Region-Division-Account | 3-0509-0312663 |
| Waste Management | WGY + Alphanumeric | WGY17110UB |
| GFL | Letter Prefix + Digits | UK829605 |
| Rumpke | 10-Digit Numeric | 4002536510 |
| Anytime Waste | 5-Digit Numeric | 24234 |
| Recology | A + 10-Digit | A0040314948 |
| City of Boise | 15-Digit | 057576800095407 |
| WillScot | 8-Digit | 10464335 |

## Performance Tiers

We track extraction rates by color code:

| Status | Rate | Meaning |
|--------|------|---------|
| 🟢 Green | 95%+ | Excellent - maintained |
| 🟡 Yellow | 80-94% | Needs improvement |
| 🔴 Red | <80% | Critical - priority fix |

## Recent Improvements (V3.1)

**50 New Vendors Added (January 2025)**

| Category | Count | Examples |
|----------|-------|----------|
| With Account Extraction | 42 | City of Meridian, Recology, WillScot |
| Invoice-Based Only | 8 | Becker360, Pete & Pete, Conigliaro |

**New Vendors with Account Numbers:**
- City of Meridian, Blue Diamond Disposal, Valley Vista, SSW Frontload
- Velpen Trucking, Gotta Go Waste, Louisiana Waste, ABC Waste
- Smith Creek, JLT Trucking, Liberty Disposal, ZARC Recycling
- 1-800-Got-Junk, Ryland Environmental, Independent Recycling, Moore Coal
- Honolulu Disposal, Pelican Waste, Great Waste, Modern Recycling
- Redgate Disposal, WG Waste, Community Waste, City of Boise
- Western Disposal, City of Jackson, Gulf Coast Containers, Amwaste
- Lexington Site Services, Gateway Disposal, TK Trash, Recology
- J&K Trash, Clean Slate, Olympic Compactor Rentals, Walker Lake Disposal
- Trident Waste, Blue Hills Environmental, Ohio Valley Waste, City Waste
- Vogel Disposal, WillScot

**New Invoice-Based Vendors:**
- Becker360, Pete & Pete, Conigliaro, D Crescio Trucking
- Community Disposal, Specialty Pallet, Premier Waste, NK Waste

## Previous Improvements (V3.0)

| Vendor | Before | After | Fix |
|--------|--------|-------|-----|
| Anytime Waste | 91.4% | 99.0% | Multiple position patterns |
| Universal Waste | 88.6% | 99.4% | LWS format handling |
| Robinson Waste | 84.4% | 96.0% | Value-before-label OCR |
| Casella | 84.4% | 95.7% | KI prefix, skip confirmations |
| Coastal Waste | 84.2% | 95.5% | Header format handling |

## Vendors Without Account Numbers

Some vendors don't use customer account numbers. They're identified by invoice number only:

**Original (16 vendors):**
- Standard Waste (scale tickets)
- Redbox+ (invoice-based)
- Boyas Recycling (invoice-based)
- Las Vegas Recycling (job numbers)
- Trash Taxi (billing system IDs)
- CRI Curbside, Rocky Ridge, Specific Waste
- Howard Disposal, Five Star Waste, Wise Environmental
- ACES Disposal, RDT Inc, Heavenly Trash
- Solid Waste Authority, Grizzly Disposal

**Added in v3.1 (8 vendors):**
- Becker360, Pete & Pete, Conigliaro
- D Crescio Trucking, Community Disposal
- Specialty Pallet, Premier Waste, NK Waste

## When Updates Are Needed

- **New vendor:** A vendor we've detected but don't have extraction logic for
- **Low extraction rate:** Green status dropping to yellow/red
- **Regional variants:** Same vendor, different format in different regions
- **Format changes:** Vendor updates their invoice format

---

# Technical Documentation

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                     INVOICE PROCESSING PIPELINE                  │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  ┌──────────────┐      ┌──────────────────────────────────────┐ │
│  │   OCR Text   │─────▶│  01_vendor_detection_module_v7.py    │ │
│  └──────────────┘      │                                      │ │
│                        │  Output: vendor_name                 │ │
│                        └──────────────┬───────────────────────┘ │
│                                       │                         │
│                                       ▼                         │
│                        ┌──────────────────────────────────────┐ │
│                        │  02_account_extraction_engine_v3.py  │ │
│                        │                                      │ │
│  ┌──────────────┐      │  ┌────────────────────────────────┐ │ │
│  │ vendor_name  │─────▶│  │     VENDOR_ACCOUNTS dict       │ │ │
│  │ + OCR text   │      │  │                                │ │ │
│  └──────────────┘      │  │  vendor → extraction_function  │ │ │
│                        │  │                                │ │ │
│                        │  │  'Waste Connections' → _extract │ │ │
│                        │  │  'Republic Services' → _extract │ │ │
│                        │  │  'GFL' → _extract_gfl          │ │ │
│                        │  │  ...164 vendors...             │ │ │
│                        │  └────────────────────────────────┘ │ │
│                        │                                      │ │
│                        │  Output: account_number or None      │ │
│                        └──────────────┬───────────────────────┘ │
│                                       │                         │
│                                       ▼                         │
│                        ┌──────────────────────────────────────┐ │
│                        │     Service Record Matching          │ │
│                        │     (account → service_id)           │ │
│                        └──────────────────────────────────────┘ │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

## File Structure

```
/mnt/project/
├── account_extraction_engine_v3.py   # Main module (this component)
├── account_extraction_module.py      # Legacy version
├── v3_yellow_fixes_checkpoint3.py    # V3 development/testing
├── account_review_interface.xlsx     # Review/management interface
├── vendor_detection_module_v7.py     # Upstream dependency
├── ocr_chunk_*.csv                   # Raw invoice OCR
└── services_chunk_*.csv              # Service records for validation
```

## Core Data Structure

```python
VENDOR_ACCOUNTS = {
    'Vendor Name': {
        'has_account': True,           # Does vendor use account numbers?
        'format': 'DDDD-NNNNNN',        # Human-readable format description
        'examples': ['3067-261791'],    # Real examples for reference
        'extract': _extract_function    # Reference to extraction function
    }
}
```

## API Reference

### extract_account(vendor_name, text)

Main extraction function.

**Parameters:**
- `vendor_name` (str): Detected vendor name from vendor_detection_module
- `text` (str): Raw OCR text from invoice

**Returns:**
- `str`: Extracted account number
- `None`: If extraction fails or vendor not configured

**Example:**
```python
from account_extraction_engine_v3 import extract_account

account = extract_account('Waste Connections', ocr_text)
# Returns: '3067-261791' or None
```

### get_account_format(vendor_name)

Get format information for a vendor.

**Returns:**
```python
{
    'has_account': True,
    'format': 'DDDD-NNNNNN',
    'examples': ['3067-261791', '2013-3110648-002']
}
```

### get_configured_vendors()

Returns list of all configured vendor names.

### get_vendor_stats()

Returns summary statistics:
```python
{
    'total_configured': 164,
    'with_accounts': 140,
    'without_accounts': 24
}
```

## Extraction Function Patterns

### Pattern 1: Direct Regex Match

For formats that appear consistently in predictable positions:

```python
def _extract_waste_connections(text: str) -> Optional[str]:
    """Format: DDDD-XXXXXX or DDDD-XXXXXX-XXX"""
    match = re.search(r'(\d{4}-\d{5,9}(?:-\d{2,3})?)', text)
    return match.group(1) if match else None
```

### Pattern 2: Line-by-Line Search

For formats where value appears after a header label:

```python
def _extract_frontier_waste(text: str) -> Optional[str]:
    """Format: 6-digit numeric after ACCOUNT #"""
    lines = text.split('\\n')  # Note: literal backslash-n
    for i, line in enumerate(lines):
        if 'ACCOUNT #' in line.upper():
            for j in range(i+1, min(i+6, len(lines))):
                val = lines[j].strip()
                if re.match(r'^\d{6}$', val):
                    return val
    return None
```

### Pattern 3: Multi-Format Handling

For vendors with regional variations:

```python
def _extract_fcc_environmental(text: str) -> Optional[str]:
    """Multiple regional formats"""
    # Tampa: TS00154796
    match = re.search(r'Customer\s*ID:\s*(TS\d{8})', text, re.I)
    if match:
        return match.group(1)
    
    # Palm Beach: PBC-3453-5
    match = re.search(r'Customer\s*ID:\s*(PBC-?\d+-?\d+)', text, re.I)
    if match:
        return match.group(1)
    
    # Houston: 5-6 digit after ACCOUNT #
    # ... additional logic
    
    return None
```

### Pattern 4: With Misdetection Filtering

When vendor detection issues can affect extraction:

```python
def _extract_waste_management(text: str) -> Optional[str]:
    """WGY format - filter misdetected vendors"""
    misdetects = ['WIN WASTE', 'WEST CENTRAL', 'BRUIN WASTE']
    if any(x in text.upper() for x in misdetects):
        return None  # Vendor detection was wrong
    
    match = re.search(r'(WGY[A-Z0-9]{5,8})', text)
    return match.group(1) if match else None
```

## OCR Text Handling

### Important: Literal Backslash-N

OCR output contains literal `\n` sequences (not actual newlines):

```python
# WRONG: Splits on nothing
lines = text.split('\n')

# RIGHT: Splits on literal backslash-n
lines = text.split('\\n')
```

### Common OCR Artifacts

| Issue | Example | Solution |
|-------|---------|----------|
| Line breaks in values | `123\n456` → `123456` | Search across lines |
| Transposed columns | Value before label | Check both directions |
| Missing spaces | `CustomerNo:` | Flexible whitespace: `\s*` |
| Extra characters | `#123456*` | Extract with capture groups |

## Testing and Validation

### Unit Testing

```python
def test_waste_connections():
    test_cases = [
        ("Account: 3067-261791 Balance:", "3067-261791"),
        ("Customer 2013-3110648-002 Active", "2013-3110648-002"),
        ("No account here", None),
    ]
    for text, expected in test_cases:
        result = _extract_waste_connections(text)
        assert result == expected
```

### Bulk Validation

```python
import pandas as pd
from account_extraction_engine_v3 import extract_account

# Load data
ocr = pd.read_csv('ocr_chunk_1.csv')
results = pd.read_csv('vendor_results.csv')
merged = ocr.merge(results, on='md5_hash')

# Test extraction for specific vendor
vendor = 'Waste Connections'
vendor_data = merged[merged['detected_vendor'] == vendor]
vendor_data['account'] = vendor_data['raw_text'].apply(
    lambda x: extract_account(vendor, x)
)

# Calculate extraction rate
total = len(vendor_data)
extracted = vendor_data['account'].notna().sum()
rate = extracted / total * 100
print(f"{vendor}: {rate:.1f}% ({extracted}/{total})")
```

### Cross-Validation with Services

```python
# Compare extracted accounts with service records
services = pd.read_csv('services_chunk_1.csv')
vendor_services = services[services['vendor_name'].str.contains(vendor, case=False)]
known_accounts = set(vendor_services['site_reference'].dropna())

# Check if extracted accounts appear in services
matches = sum(1 for acc in vendor_data['account'].dropna() 
              if acc in known_accounts)
match_rate = matches / len(vendor_data['account'].dropna()) * 100
print(f"Service match rate: {match_rate:.1f}%")
```

## Troubleshooting

| Symptom | Likely Cause | Solution |
|---------|--------------|----------|
| Returns None for all | Wrong line split (`\n` vs `\\n`) | Fix split character |
| Low extraction rate | Regional format variations | Add alternate patterns |
| Wrong value extracted | Pattern too generic | Narrow with exact digit counts |
| Some vendors fail | Vendor misdetection | Check upstream vendor detection |
| Format changed | Vendor updated invoices | Update pattern, add new format |

## Performance Optimization

The module processes ~67,000 invoices. Optimization strategies:

1. **Compiled Regex:** Frequently-used patterns are pre-compiled
2. **Early Return:** Functions return immediately on first match
3. **Line Limits:** Only search first N lines for header-based patterns
4. **Format Ordering:** Most common formats checked first

## Maintenance Workflow

### Adding a New Vendor

1. Get 5-10 sample invoices from vendor
2. Identify account format and position
3. Create extraction function with docstring
4. Add to VENDOR_ACCOUNTS dictionary
5. Test against all samples
6. Validate against services data
7. Update documentation

### Improving Extraction Rate

1. Identify failing invoices for vendor
2. Analyze OCR text patterns
3. Identify new format variations
4. Add alternate patterns to extraction function
5. Re-test full vendor dataset
6. Update extraction rate tracking

---

## Related Documentation

- `02_account_extraction_INSTRUCTIONS.md` - Claude instructions for pattern updates
- `01_vendor_detection_README.md` - Upstream vendor detection
- `v3_yellow_fixes_checkpoint3.py` - V3 development history

---

## Change Log

| Version | Date | Changes |
|---------|------|---------|
| v3.2 | Jan 2026 | Maintenance updates, 164 vendors, 95.9% extraction rate |
| v3.1 | Jan 2025 | Added 50 new vendors (42 with accounts, 8 invoice-based), 164 total configured |
| v3.0 | Dec 2024 | Yellow tier fixes, regional formats, 92.5% avg rate |
| v2 | Nov 2024 | Pattern-based refactor, 85% avg rate |
| v1 | Oct 2024 | Initial implementation, 70% avg rate |

---

## Appendix: Complete Vendor Format Reference

### Tier 1 (>2,000 invoices)

| Vendor | Format | Example |
|--------|--------|---------|
| Waste Connections | DDDD-NNNNNN[-NNN] | 3067-261791 |
| Anytime Waste | NNNNN | 24234 |
| Republic Services | D-DDDD-DDDDDDD | 3-0509-0312663 |
| Waste Management | WGYXXXXXXXX | WGY17110UB |
| GFL | XX######(#) | UK829605 |

### Tier 2 (1,000-2,000 invoices)

| Vendor | Format | Example |
|--------|--------|---------|
| Rumpke | NNNNNNNNNN | 4002536510 |
| Waste Pro | NNNNNN(N) | 753008 |
| Cockey's Enterprises | NNNNN[-NNN] | 13010-007 |
| Universal Waste | NNNNNN | 273586 |

### Tier 3 (500-1,000 invoices)

| Vendor | Format | Example |
|--------|--------|---------|
| Robinson Waste | NNNNN.NNN | 55779.64 |
| Hamilton Alliance | NNNN | 1042 |
| Active Waste | NNNNN | 32650 |
| Priority Waste | PWNNNNNNNN | PW00011457 |
| Casella | NN-NNNNN N | 81-39019 6 |
| Boren Brothers | NNNNNN | 005881 |
| Aspen Waste | N-NNNNN N | 4-82600 2 |

### Tier 4 (200-500 invoices)

| Vendor | Format | Example |
|--------|--------|---------|
| Meridian Waste | NN-NNNNNNN N | 01-1276236 4 |
| Frontier Waste | NNNNNN | 207779 |
| FCC Environmental | TS########, PBC-NNNN-N | TS00154796 |
| SmartTrash | CNNNNN | C02096 |
| LRS | NNNNN.NN | 12949.1 |
| 121 Disposal | 121NNNNN | 12115904 |
| Best Cleaner | NNNNNNNNNNNN | 621620359356 |

### New in v3.1 (50-200 invoices)

| Vendor | Format | Example |
|--------|--------|---------|
| City of Meridian | NNNNNNNN-NN | 99011222-01 |
| Blue Diamond Disposal | NNNNN | 30239 |
| Valley Vista | VV-NNNNNN N | VV-478887 7 |
| Smith Creek | XXXXNNNN | WAST0004 |
| 1-800-Got-Junk | NNN | 990 |
| Recology | ANNNNNNNNNNN | A0040314948 |
| Honolulu Disposal | NNNNNNNNNN | 2131885000 |
| City of Boise | NNNNNNNNNNNNNNN | 057576800095407 |
| WillScot | NNNNNNNN | 10464335 |
| City of Jackson | NNNNNN-NNNNN | 203809-21438 |
| Olympic Compactor Rentals | NN-NNNNNNN | 01-0080240 |
| TK Trash | NN-NNNNNN N | 75-602470 5 |
| Trident Waste | NN-NNNNN N | 01-35884 5 |
| Community Waste | NN-NNNNNN N | 10-271295 7 |
| Lexington Site Services | NNNNNNNNN | 220009602 |
