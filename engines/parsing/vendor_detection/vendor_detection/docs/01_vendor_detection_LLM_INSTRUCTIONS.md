# Vendor Detection Module - Claude Instructions

## Purpose

This document provides all context needed for Claude to efficiently update regex patterns in the vendor detection module. Load this document whenever you need to add new vendors, fix misdetections, or update existing patterns.

---

## Module Overview

**File:** `/mnt/project/vendor_detection_module_v9.py`
**Function:** Identify waste management vendor names from invoice OCR text
**Current Performance:** 97.1% detection rate
**Pattern Count:** 892 vendor patterns  

---

## Data Files Reference

| File | Purpose | Key Columns |
|------|---------|-------------|
| `ocr_chunk_*.csv` (1-7) | Raw OCR text from invoices | `md5_hash`, `source_file`, `raw_text` |
| `vendor_results.csv` | Current detection results | `md5_hash`, `source_file`, `detected_vendor` |
| `exceptions_to_review_v2.csv` | Undetected invoices to analyze | `md5_hash`, `vendor_name`, `count`, `preview` |
| `services_chunk_*.csv` (1-2) | Service records for validation | `vendor_name`, `service_address`, `equipment_type` |
| `billing_chunk_*.csv` (1-6) | Billing records with vendor names | `vendor_name`, `billing_reference`, `charge_description` |

---

## Critical Rules

### 1. Pattern Order Matters

The `detect_vendor()` function returns the **FIRST match**. This means:

```python
# BAD: Generic pattern before specific
'Waste Management': r'WASTE\s*MANAGEMENT',  # Line 288 - catches everything
'Win Waste': r'WIN\s*WASTE',                 # Never matches (if after WM)

# GOOD: Specific patterns before generic
'Win Waste': r'WIN\s*WASTE',                 # Line 35 - catches Win Waste first
'Waste Management': r'WASTE\s*MANAGEMENT',   # Line 288 - catches only real WM
```

**The most important rule:** Any vendor whose invoice text contains "WASTE MANAGEMENT" but is NOT Waste Management must have its pattern placed **BEFORE line 288** (the Waste Management pattern).

### 2. OCR Text Preprocessing

The detection function normalizes text before matching:
- Converts to uppercase
- Replaces literal `\n` sequences with spaces
- Does NOT strip punctuation (apostrophes, dashes, etc. remain)

```python
text_upper = str(text).replace(chr(92) + "n", " ").upper()
```

### 3. Regex Pattern Guidelines

| Scenario | Pattern Approach | Example |
|----------|-----------------|---------|
| Company name with spaces | Use `\s*` between words | `WASTE\s*CONNECTIONS` |
| Optional words | Use `(word)?` or `(word|alt)?` | `GFL\s*(ENVIRONMENTAL)?` |
| Apostrophes in names | Use `\'?` (escaped optional) | `HARTER\'?S` |
| Multi-word variants | Use alternation `\|` | `BORO\s*WIDE\|BOROWIDE` |
| OCR line breaks | Use `.*` or `\s+` | `GRAND.*RAPIDS.*IRON` |
| Unique identifier | Short distinctive string | `GILTON` (not full name) |

### 4. Avoid Over-Matching

Patterns should be specific enough to avoid false positives:

```python
# BAD: Too generic, matches other vendors
'Waste': r'WASTE'  # Matches "Win Waste", "Apex Waste", etc.

# GOOD: Specific enough to be unique
'Waste Connections': r'WASTE\s*CONNECTIONS'
```

---

## Workflow: Adding New Vendors

### Step 1: Identify the Vendor

Look for distinctive text in the OCR that uniquely identifies the vendor:
- Company name in header/letterhead
- Website domain (e.g., `wm.com`, `republicservices.com`)
- Unique account number formats
- Phone numbers or addresses

### Step 2: Create the Pattern

Start with the most distinctive part of the vendor name:

```python
# From OCR: "HOMETOWN SANITATION SERVICES LLC"
'Hometown Sanitation': r'HOMETOWN\s*SANITATION',

# From OCR: "Kohlmorgan Hauling"  
'Kohlmorgan Hauling': r'KOHLMORGAN',  # Just the unique name is enough
```

### Step 3: Determine Placement

**Check if the invoice text contains any of these strings:**
- "WASTE MANAGEMENT" → Place BEFORE line 288
- "REPUBLIC SERVICES" → Check for conflicts
- "GFL" → Check for conflicts

**Otherwise:** Place alphabetically in the appropriate batch section.

### Step 4: Test the Pattern

```python
import re

test_text = """YOUR OCR TEXT HERE"""
pattern = r'YOUR_PATTERN_HERE'

if re.search(pattern, test_text.upper()):
    print("✓ Pattern matches")
else:
    print("✗ Pattern doesn't match")
```

---

## Common Issues and Fixes

### Issue 1: Misdetection (Wrong Vendor Matched)

**Symptom:** Invoice from Vendor A is detected as Vendor B

**Cause:** Vendor B's pattern is too generic OR positioned before Vendor A's

**Fix:**
1. Find Vendor B's pattern line number
2. Add Vendor A's more specific pattern BEFORE Vendor B
3. Or make Vendor B's pattern more specific

**Example Fix (WM Misdetections):**
```python
# These vendors contain "WASTE MANAGEMENT" in their text
# MUST be before 'Waste Management': r'WASTE\s*MANAGEMENT'

'Bruin Waste Management': r'BRUIN\s*WASTE',  # Specific first
'Heartland Waste Management': r'HEARTLAND\s*(WASTE|WM)',
'Waste Management': r'WASTE\s*MANAGEMENT',   # Generic last
```

### Issue 2: Non-Detection (Returns OTHER)

**Symptom:** Invoice not matched, returns "OTHER"

**Cause:** No pattern exists, or pattern doesn't match OCR variations

**Fix:**
1. Review the OCR text for the distinctive vendor identifier
2. Check for OCR artifacts (line breaks, misspellings)
3. Create a robust pattern that handles variations

**Example:**
```python
# OCR shows: "GRAND\nRAPIDS\nIRON" (split across lines)
# Fix: Use .* to bridge potential splits
'Grand Rapids Iron': r'GRAND.*RAPIDS.*IRON',
```

### Issue 3: Apostrophe/Special Character Issues

**Symptom:** Pattern doesn't match due to OCR-specific character handling

**Fix:** Make special characters optional or use wildcards

```python
# OCR might show: SALANDRO'S, SALANDROS, or SALANDRO S
'Salandro Refuse': r'SALANDRO',  # Just match the unique part
```

---

## Module Structure

```python
VENDOR_PATTERNS = {
    # ============================================================
    # WASTE MANAGEMENT MISDETECTION FIXES - MUST BE BEFORE WM PATTERN
    # ============================================================
    # Lines 29-67: Patterns for vendors that contain "WASTE MANAGEMENT"
    
    # ============================================================
    # CORE VENDORS (A-Z)
    # ============================================================
    # Lines 69-298: Main vendor patterns alphabetically
    
    # NOTE: 'Waste Management' is at LINE 288
    
    # === BATCH 1-10 ADDITIONS ===
    # Lines 300-838: Additional vendors added in batches
}

def detect_vendor(text):
    """Detect vendor from invoice OCR text. Returns vendor name or 'OTHER'."""
    if not text or str(text) == 'nan':
        return 'OTHER'
    text_upper = str(text).replace(chr(92) + "n", " ").upper()
    for vendor, pattern in VENDOR_PATTERNS.items():
        if re.search(pattern, text_upper):
            return vendor
    return 'OTHER'
```

---

## Validation Approach

After updating patterns, validate with:

```python
import pandas as pd
from vendor_detection_module_v9 import detect_vendor

# Load OCR data
ocr = pd.read_csv('ocr_chunk_1.csv')

# Test detection
ocr['detected'] = ocr['raw_text'].apply(detect_vendor)

# Check specific vendor counts
print(ocr['detected'].value_counts())
```

---

## Quick Reference: Adding a New Vendor

```python
# 1. Find the vendor in exceptions or OCR data
# 2. Identify distinctive text (company name, unique identifiers)
# 3. Create pattern:

'New Vendor Name': r'UNIQUE\s*IDENTIFIER',

# 4. Check placement:
#    - Contains "WASTE MANAGEMENT"? → Before line 288
#    - Otherwise → Alphabetically or in next batch section

# 5. Test pattern matches expected invoices
# 6. Verify no false positives with other vendors
```

---

## Related Modules

| Module | Purpose | Dependency |
|--------|---------|------------|
| `02_account_extraction` | Extract account numbers | Uses vendor name to select extractor |
| `03_line_items_equipment_material` | Extract equipment/materials | Uses vendor name for parsing rules |
| `04_line_items_charge_description` | Extract charge details | Uses vendor name for format rules |

**Important:** Vendor detection is the **routing key** for all downstream extraction. Incorrect vendor detection cascades to wrong extraction logic.

---

## Performance Targets

| Metric | Current | Target |
|--------|---------|--------|
| Detection Rate | 97.1% | 98%+ |
| Misdetection Rate | <0.5% | <0.1% |
| Pattern Count | 892 | As needed |

---

## Version History

| Version | Changes | Detection Rate |
|---------|---------|----------------|
| v9 | Added 142 patterns, ML-assisted workflow | 97.1% |
| v8 | Pattern optimization, batch additions | 96.5% |
| v7 | Fixed 317 WM misdetections | 95.5% |
| v6 | Added 110+ new vendors | 95.5% |
| v5 | Added 150+ vendors, fixed OCR patterns | 93.7% |

---

## Contact & Ownership

**Owner:** Shane @ Wasteology
**Module:** Invoice Processing System - Vendor Detection
**Last Updated:** January 2026
