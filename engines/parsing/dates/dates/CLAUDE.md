# Date Extraction Module - Claude Context

> **Parent Context**: Always read `/home/scstclair/projects/CLAUDE.md` first for full project awareness.

## Module Purpose

Extract invoice/statement dates from raw OCR text using **vendor-specific patterns**.

## Core Principle

**VENDOR DEFINES THE INVOICE FORMAT.**

Every vendor has a unique invoice layout. Generic patterns fail because:
- "Date" can mean invoice date, due date, service date, or payment date
- Label positions vary (inline, columnar, above, below)
- Date formats vary (MM/DD/YY, Month DD YYYY, DD-Mon-YYYY, etc.)

> [!IMPORTANT]
> **ALWAYS VERIFY CHANGES WERE SUCCESSFUL.**
>
> After every edit, file write, or configuration change, verify the change was applied correctly
> by reading the file back. Never assume success - confirm it before proceeding.

> [!CAUTION]
> **ALWAYS RE-READ THE PLAN FILE AT SESSION START.**
>
> When continuing work, re-read `PLAN_date_extraction.md` before doing anything else.
> Follow the plan exactly - no shortcuts. Update the plan after each milestone.
> Do not rely on context summaries - they may be incomplete.
> Commit on the schedule specified in the plan.

## Current Status

| Metric | Value |
|--------|-------|
| Vendors Configured | 1113 |
| Module Version | v3.27 |
| Target | 1 pattern per vendor in vendor_detection module |

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                    DATE EXTRACTION FLOW                          │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│   Raw OCR Text ──► detect_vendor() ──► vendor name               │
│                                              │                   │
│                                              ▼                   │
│                         VENDOR_DATE_ADDITIONS[vendor]['extract'] │
│                                              │                   │
│                                              ▼                   │
│                                    vendor-specific extractor     │
│                                              │                   │
│                                              ▼                   │
│                                      YYYY-MM-DD or None          │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

## Key Files

| File | Purpose |
|------|---------|
| `date_extraction_additions.py` | **PRIMARY** - 240 vendor extractors + VENDOR_DATE_ADDITIONS dict |
| `date_extraction_engine.py` | Generic fallback patterns (legacy) |
| `__init__.py` | Module exports, version tracking |

---

## Methodology: Adding New Vendor Patterns

### Step 1: Identify Unconfigured Vendors

```python
# Find vendors in vendor_detection but not in date extraction
import sys
sys.path.insert(0, '.')
from vendor_detection.data.vendor_detection_module_v9 import detect_vendor
from dates.date_extraction_additions import VENDOR_DATE_ADDITIONS
from collections import Counter

configured = set(VENDOR_DATE_ADDITIONS.keys())
unconfigured_counts = Counter()

with open('training_data/ocr_chunks/raw_ocr_text.csv', 'r') as f:
    reader = csv.DictReader(f)
    for i, row in enumerate(reader):
        if i >= 50000:
            break
        text = row.get('raw_text', '')
        vendor = detect_vendor(text)
        if vendor and vendor not in configured and vendor != 'OTHER':
            unconfigured_counts[vendor] += 1

# Top unconfigured by invoice volume
for vendor, count in unconfigured_counts.most_common(20):
    print(f"{vendor}: {count}")
```

### Step 2: Get Sample Invoice Text

```python
# Get sample for specific vendor
target_vendor = 'Example Waste'
with open('training_data/ocr_chunks/raw_ocr_text.csv', 'r') as f:
    reader = csv.DictReader(f)
    for row in reader:
        text = row.get('raw_text', '')
        if detect_vendor(text) == target_vendor:
            # CRITICAL: Normalize literal \n to actual newlines for viewing
            text = text.replace('\\n', '\n')
            lines = text.split('\n')
            for i, line in enumerate(lines[:25]):
                print(f'{i:3}: {line[:70]}')
            break
```

### Step 3: Identify Pattern Type

Analyze the sample to determine:

1. **Date Label**: What text precedes the date?
   - "Invoice Date", "Statement Date", "Bill Date", "DATE", "Date:", etc.

2. **Label Position**: Where is the label relative to the value?
   - **Inline**: `Invoice Date: 01/15/2025` (same line)
   - **Columnar**: Label on one line, value on next
   - **Wide Columnar**: Label and value separated by 5-10 lines
   - **Reverse Columnar**: Value ABOVE the label (rare)

3. **Date Format**: How is the date formatted?
   - `MM/DD/YY` or `MM/DD/YYYY`
   - `M/D/YYYY` (no leading zeros)
   - `Month DD, YYYY` (January 15, 2025)
   - `Mon DD, YYYY` (Jan 15, 2025)
   - `DD-Mon-YYYY` (15-Jan-2025)
   - `MM-DD-YYYY` (dashes instead of slashes)
   - `Weekday Mon DD, YYYY` (Tue Mar 25, 2025)

### Step 4: Write the Extractor Function

**CRITICAL**: Always use `_normalize_text()` for columnar patterns!

```python
def _normalize_text(text: str) -> str:
    """Normalize OCR text by converting literal \\n to actual newlines."""
    return text.replace('\\n', '\n')
```

#### Pattern Templates

**Inline Pattern** (label and value on same line):
```python
def _extract_example_waste_date(text: str) -> Optional[str]:
    """Example Waste - Invoice Date: MM/DD/YYYY inline"""
    text = _normalize_text(text)
    m = re.search(r'Invoice\s+Date:\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})', text, re.IGNORECASE)
    if m:
        return _parse_date_match(m, 'MDY')
    return None
```

**Columnar Pattern** (label on one line, value on next):
```python
def _extract_example_waste_date(text: str) -> Optional[str]:
    """Example Waste - DATE columnar MM/DD/YYYY"""
    text = _normalize_text(text)  # CRITICAL!
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if line.strip().upper() == 'DATE':
            for j in range(i + 1, min(i + 5, len(lines))):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None
```

**Wide Columnar Pattern** (label and value separated by 5-10 lines):
```python
def _extract_example_waste_date(text: str) -> Optional[str]:
    """Example Waste - STATEMENT DATE columnar MM/DD/YY (wide spacing)"""
    text = _normalize_text(text)  # CRITICAL!
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if 'STATEMENT DATE' in line.upper():
            for j in range(i + 1, min(i + 10, len(lines))):  # Extended range
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None
```

**Reverse Columnar Pattern** (value BEFORE label):
```python
def _extract_example_waste_date(text: str) -> Optional[str]:
    """Example Waste - DATE label appears AFTER date value"""
    text = _normalize_text(text)
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if line.strip().upper() == 'DATE':
            # Date value is on the line BEFORE the DATE label
            for j in range(max(0, i - 3), i):
                m = re.match(r'^\s*(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*$', lines[j].strip())
                if m:
                    return _parse_date_match(m, 'MDY')
    return None
```

**Month Name Pattern**:
```python
def _extract_example_waste_date(text: str) -> Optional[str]:
    """Example Waste - Date: Month DD, YYYY inline"""
    text = _normalize_text(text)
    m = re.search(r'Date:\s*([A-Za-z]+)\s+(\d{1,2}),?\s*(\d{4})', text, re.IGNORECASE)
    if m:
        month = MONTH_MAP.get(m.group(1).lower()[:3])
        if month:
            day, year = int(m.group(2)), int(m.group(3))
            if _validate_date(month, day, year):
                return _format_date(month, day, year)
    return None
```

### Step 5: Add Dictionary Entry

```python
VENDOR_DATE_ADDITIONS = {
    # ... existing entries ...
    'Example Waste': {
        'format': 'MM/DD/YYYY',
        'label': 'Invoice Date:',
        'examples': ['01/15/2025'],
        'extract': _extract_example_waste_date
    },
}
```

### Step 6: Test the Pattern

```python
# Test single vendor
import sys
sys.path.insert(0, '.')
from vendor_detection.data.vendor_detection_module_v9 import detect_vendor
from dates.date_extraction_additions import VENDOR_DATE_ADDITIONS

target = 'Example Waste'
with open('training_data/ocr_chunks/raw_ocr_text.csv', 'r') as f:
    reader = csv.DictReader(f)
    for row in reader:
        text = row.get('raw_text', '')
        if detect_vendor(text) == target:
            extractor = VENDOR_DATE_ADDITIONS[target]['extract']
            result = extractor(text)
            print(f'{target}: {result}')
            break
```

---

## Common Issues & Fixes

### Issue: Pattern Returns None

**Cause 1**: OCR text has literal `\n` instead of actual newlines
```python
# WRONG - splits on actual newlines, but OCR has literal \n
lines = text.split('\n')

# RIGHT - normalize first
text = _normalize_text(text)
lines = text.split('\n')
```

**Cause 2**: Wide columnar spacing
```python
# WRONG - only searches 5 lines after label
for j in range(i + 1, min(i + 5, len(lines))):

# RIGHT - extend search range for wide layouts
for j in range(i + 1, min(i + 10, len(lines))):
```

**Cause 3**: Label contains partial match
```python
# WRONG - "INVOICE DATE" also matches "DUE DATE" substring issues
if 'DATE' in line.upper():

# RIGHT - be more specific
if 'INVOICE DATE' in line.upper():
# or for exact match
if line.strip().upper() == 'DATE':
```

**Cause 4**: Date format mismatch
```python
# WRONG - expects MM/DD/YYYY but vendor uses MM-DD-YYYY
m = re.match(r'(\d{2})/(\d{2})/(\d{4})', ...)

# RIGHT - allow both separators
m = re.match(r'(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})', ...)
```

### Issue: Wrong Date Extracted

**Cause**: Multiple date fields, extracting wrong one (due date instead of invoice date)
```python
# Be specific about which date label to match
# Prefer: Invoice Date, Statement Date, Bill Date
# Avoid: Due Date, Payment Date, Service Date (unless that's all vendor has)
```

---

## Tranche Development Process

Patterns are added in tranches of 10-12 vendors for manageable commits:

1. **Sample Collection**: Run sampling script to find top unconfigured vendors
2. **Pattern Analysis**: Review samples, identify pattern types
3. **Implementation**: Write extractor functions + dict entries
4. **Testing**: Test all patterns in tranche before commit
5. **Fix Failures**: Debug and fix any failing patterns
6. **Commit**: Commit with tranche number and vendor list

```bash
# Example commit message
git commit -m "[feature]: Date extraction - 240 vendors (Tranches 21-24)"
```

---

## Helper Functions Reference

```python
def _normalize_text(text: str) -> str:
    """Convert literal \\n to actual newlines."""
    return text.replace('\\n', '\n')

def _parse_date_match(m: re.Match, format: str) -> Optional[str]:
    """Parse regex match to YYYY-MM-DD. Format: 'MDY', 'DMY', 'YMD'."""

def _validate_date(month: int, day: int, year: int) -> bool:
    """Validate date is reasonable (2020-2030, valid month/day)."""

def _format_date(month: int, day: int, year: int) -> str:
    """Format as YYYY-MM-DD string."""

MONTH_MAP = {'jan': 1, 'feb': 2, ...}  # Month name to number
```

---

## Goal

**100% coverage**: Every vendor in `vendor_detection_module_v9.py` should have a corresponding date extraction pattern in `VENDOR_DATE_ADDITIONS`.

Current: 1094 vendors configured
Target: ~1,177 vendors (matching vendor_detection count)

---

*Last updated: February 2026 (v3.27 - 1113 vendors)*
