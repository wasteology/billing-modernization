# 01 Vendor Detection Module

## Overview

The Vendor Detection Module is the first stage of Wasteology's invoice processing pipeline. It identifies which waste management vendor issued an invoice by analyzing OCR-extracted text. This detection serves as the routing key for all downstream extraction logic.

---

# Business Documentation

## What It Does

When Wasteology receives a hauler invoice, we scan it and extract the text using OCR. This module reads that text and determines which of our 700+ vendor partners issued the invoice.

**Example:**
```
Invoice Text: "REPUBLIC SERVICES - Invoice #12345..."
Detection Result: "Republic Services"
```

## Why It Matters

1. **Service Matching:** Each vendor has a different account number format. Knowing the vendor tells us which extraction rules to apply.

2. **Billing Reconciliation:** We match invoices to existing service records. Wrong vendor = wrong match.

3. **Client Reporting:** Our clients expect accurate vendor attribution on their billing statements.

## Current Performance

| Metric | Value |
|--------|-------|
| **Detection Rate** | 97.1% |
| **Invoices Processed** | 67,161 |
| **Vendors Recognized** | 892 |
| **Unmatched Invoices** | 1,946 (2.9%) |

## Top Vendors by Volume

| Rank | Vendor | Invoice Count | % of Total |
|------|--------|--------------|------------|
| 1 | Waste Connections | 15,609 | 23.2% |
| 2 | Anytime Waste | 3,226 | 4.8% |
| 3 | Republic Services | 2,811 | 4.2% |
| 4 | Waste Management | 2,439 | 3.6% |
| 5 | GFL | 2,435 | 3.6% |
| 6 | Rumpke | 1,474 | 2.2% |
| 7 | Waste Pro | 1,234 | 1.8% |
| 8 | Cockey's Enterprises | 1,148 | 1.7% |
| 9 | Universal Waste | 1,044 | 1.6% |
| 10 | Robinson Waste | 947 | 1.4% |

## When Updates Are Needed

- **New vendor appears:** An invoice from a vendor we haven't seen before
- **Misdetection:** Invoice incorrectly attributed to wrong vendor
- **Detection failure:** Invoice returns "OTHER" but we can identify the vendor

## How to Request Updates

1. Identify the invoice(s) with the issue
2. Note the MD5 hash or source file
3. Provide the expected vendor name
4. Submit via the vendor review interface (Excel)

---

# Technical Documentation

## Architecture

```
┌─────────────────┐
│   OCR Text      │
│   (raw_text)    │
└────────┬────────┘
         │
         ▼
┌─────────────────────────────────────────┐
│       vendor_detection_module_v9.py      │
│                                          │
│  ┌───────────────────────────────────┐  │
│  │      VENDOR_PATTERNS dict         │  │
│  │                                   │  │
│  │  'Waste Connections': r'WASTE\s*  │  │
│  │   CONNECTIONS'                    │  │
│  │  'Republic Services': r'REPUBLIC  │  │
│  │   \s*SERVICES'                    │  │
│  │  ...750+ patterns...              │  │
│  └───────────────────────────────────┘  │
│                                          │
│  ┌───────────────────────────────────┐  │
│  │        detect_vendor(text)         │  │
│  │                                   │  │
│  │  1. Normalize text (uppercase,    │  │
│  │     handle \n sequences)          │  │
│  │  2. Iterate through patterns      │  │
│  │  3. Return FIRST match            │  │
│  │  4. Or return 'OTHER'             │  │
│  └───────────────────────────────────┘  │
└─────────────────────────────────────────┘
         │
         ▼
┌─────────────────┐
│ Detected Vendor │
│ (vendor_name)   │
└─────────────────┘
```

## File Structure

```
/mnt/project/
├── vendor_detection_module_v9.py    # Main module (this component)
├── vendor_results.csv               # Detection results for all invoices
├── exceptions_to_review_v2.csv      # Undetected invoices for analysis
├── ocr_chunk_*.csv                  # Raw OCR text (7 files, 67k invoices)
├── services_chunk_*.csv             # Service records for validation
└── vendor_detection_fix_wm_misdetections.md  # Example fix documentation
```

## Core Function

```python
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

## Pattern Dictionary Structure

```python
VENDOR_PATTERNS = {
    # === MISDETECTION FIXES (lines 29-67) ===
    # Patterns for vendors that could be confused with major vendors
    # MUST be positioned before the generic patterns
    'Bruin Waste Management': r'BRUIN\s*WASTE',  # Before 'Waste Management'
    'Win Waste': r'WIN\s*WASTE',
    
    # === CORE VENDORS A-Z (lines 69-298) ===
    '121 Disposal': r'121\s*DISPOSAL',
    'A-1 Disposal': r'A-?1\s*DISPOSAL',
    # ... alphabetical order ...
    'Waste Connections': r'WASTE\s*CONNECTIONS',
    'Waste Management': r'WASTE\s*MANAGEMENT',  # LINE 288 - CRITICAL
    
    # === BATCH ADDITIONS (lines 300-838) ===
    # Additional vendors added incrementally
}
```

## Key Technical Considerations

### 1. First-Match Returns

Python dictionaries maintain insertion order. The detection function iterates through patterns and returns on first match. This means **pattern order is critical**:

```python
# If 'Waste Management' comes before 'Bruin Waste Management':
# "BRUIN WASTE MANAGEMENT" → matches "Waste Management" ❌

# If 'Bruin Waste Management' comes first:
# "BRUIN WASTE MANAGEMENT" → matches "Bruin Waste Management" ✓
```

### 2. OCR Text Normalization

Before matching, text is:
- Converted to uppercase
- Literal `\n` sequences replaced with spaces (handles OCR artifacts)
- NOT stripped of punctuation

### 3. Regex Best Practices

| Use Case | Pattern | Example |
|----------|---------|---------|
| Word boundary | `\s*` or `\s+` | `WASTE\s*CONNECTIONS` |
| Optional word | `(word)?` | `GFL\s*(ENVIRONMENTAL)?` |
| Alternation | `\|` | `BORO\s*WIDE\|BOROWIDE` |
| Any character | `.` or `.*` | `GRAND.*RAPIDS.*IRON` |
| Optional apostrophe | `\'?` | `HARTER\'?S` |

### 4. Performance Characteristics

| Metric | Value |
|--------|-------|
| Patterns | 892 |
| Avg. detection time | <1ms per invoice |
| Memory footprint | Minimal (compiled regex) |

## Data Pipeline Integration

```
┌──────────────┐     ┌──────────────┐     ┌──────────────┐     ┌──────────────┐
│   01_VENDOR  │────▶│ 02_ACCOUNT   │────▶│ 03_LINE_ITEM │────▶│ 04_CHARGES   │
│   DETECTION  │     │  EXTRACTION  │     │  EQUIPMENT   │     │ DESCRIPTION  │
└──────────────┘     └──────────────┘     └──────────────┘     └──────────────┘
       │
       │ vendor_name determines:
       ▼
  ┌─────────────────────────────────────────────────────┐
  │ • Which account extraction function to use          │
  │ • Which line item parsing rules apply               │
  │ • Which charge categorization logic to use          │
  │ • How to match to service records                   │
  └─────────────────────────────────────────────────────┘
```

## Testing

### Unit Test Pattern

```python
def test_vendor_detection():
    test_cases = [
        ("WASTE CONNECTIONS Invoice #123", "Waste Connections"),
        ("Republic Services - Statement", "Republic Services"),
        ("BRUIN WASTE MANAGEMENT", "Bruin Waste Management"),  # Not WM
        ("Random text without vendor", "OTHER"),
    ]
    
    for text, expected in test_cases:
        result = detect_vendor(text)
        assert result == expected, f"Failed: {text} → {result} (expected {expected})"
```

### Bulk Validation

```python
import pandas as pd
from vendor_detection_module_v7 import detect_vendor

# Load and test
ocr = pd.read_csv('ocr_chunk_1.csv')
ocr['detected'] = ocr['raw_text'].apply(detect_vendor)

# Validation metrics
total = len(ocr)
detected = len(ocr[ocr['detected'] != 'OTHER'])
print(f"Detection rate: {detected/total*100:.1f}%")
```

## Maintenance

### Adding a New Vendor

1. **Locate distinctive text** in OCR sample
2. **Create pattern** using regex best practices
3. **Determine placement:**
   - Contains "WASTE MANAGEMENT"? → Before line 288
   - Otherwise → In appropriate batch section
4. **Test** against known invoices
5. **Validate** no false positives

### Fixing Misdetections

1. **Identify the wrong pattern** being matched
2. **Create more specific pattern** for correct vendor
3. **Place specific pattern BEFORE generic one**
4. **Retest** both vendors' invoices

### Version Control

Each major update should:
- Increment version number in module docstring
- Document changes in version history
- Update detection rate metrics
- Create fix documentation (like `vendor_detection_fix_wm_misdetections.md`)

## Troubleshooting

| Symptom | Likely Cause | Solution |
|---------|--------------|----------|
| Invoice returns OTHER | No pattern exists | Add new pattern |
| Wrong vendor matched | Pattern order issue | Move specific pattern before generic |
| Pattern doesn't match | OCR variations | Make pattern more flexible |
| Performance degraded | Too many patterns | Optimize regex compilation |

---

## API Reference

### detect_vendor(text)

**Parameters:**
- `text` (str): Raw OCR text from invoice

**Returns:**
- `str`: Vendor name if matched, "OTHER" if no match

**Example:**
```python
from vendor_detection_module_v7 import detect_vendor

vendor = detect_vendor("WASTE CONNECTIONS Invoice #12345")
# Returns: "Waste Connections"
```

### get_vendor_count()

**Returns:**
- `int`: Total number of patterns in VENDOR_PATTERNS

**Example:**
```python
from vendor_detection_module_v7 import get_vendor_count

count = get_vendor_count()
# Returns: 750 (or current count)
```

---

## Related Documentation

- `01_vendor_detection_INSTRUCTIONS.md` - Claude instructions for pattern updates
- `vendor_detection_fix_wm_misdetections.md` - Example fix documentation
- `account_extraction_engine_v3.py` - Downstream account extraction

---

## Change Log

| Version | Date | Changes | Detection Rate |
|---------|------|---------|----------------|
| v9 | Jan 2026 | Added 142 patterns, ML-assisted workflow | 97.1% |
| v8 | Dec 2025 | Pattern optimization, batch additions | 96.5% |
| v7 | Dec 2024 | Fixed 317 WM misdetections | 95.5% |
| v6 | Dec 2024 | Added 110+ new vendors | 95.5% |
| v5 | Nov 2024 | Added 150+ vendors, fixed OCR patterns | 93.7% |
| v4 | Nov 2024 | Initial production release | 91.2% |
