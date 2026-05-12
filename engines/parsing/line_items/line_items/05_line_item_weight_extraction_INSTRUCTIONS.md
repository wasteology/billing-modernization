# Line Item Extraction (Weight/Tonnage) - Claude Instructions

## Purpose

This document provides all context needed for Claude to build and maintain weight extraction patterns for on-call services (Open Top, Compactor). These services are always weighed at the destination facility, and the weight appears on the invoice.

**Critical Rule**: On-call services (Open Top, Compactor) MUST have actual weight from invoice. Calculated weights are NOT used for these equipment types.

---

## Module Overview

**File:** `/mnt/project/line_items/weight_extraction_module.py` (to be created)
**Function:** Extract actual tonnage from invoice line items for on-call services
**Target Equipment:** Open Top, Compactor (all types), Roll-Off
**Output Fields:** `weight_tons`, `weight_source`

---

## Reference Documents

| Document | Location | Purpose |
|----------|----------|---------|
| Weight Instructions | `/home/scstclair/projects/NG Report/Weight Instructions.md` | Business rules for weight handling |
| Line Item Extraction | `03_line_item_equipment_material_INSTRUCTIONS.md` | Pattern for vendor-specific extraction |

---

## Business Rules (from Weight Instructions.md)

### Equipment Classification

| Equipment Type | Size Range | Weight Method |
|----------------|------------|---------------|
| Front Load | 1-12 YD | **Calculated** (recurring) |
| Toter/Cart | Gallons | **Calculated** (recurring) |
| Open Top | 15-45 YD | **Actual from invoice** (on-call) |
| Compactor | Any | **Actual from invoice** (on-call) |
| Roll-Off | 15-45 YD | **Actual from invoice** (on-call) |

### Key Rules

1. **All containers < 15 YD** = Recurring/scheduled = Calculated weight
2. **All containers >= 15 YD** = On-call = Actual weight from invoice
3. **All compactors** = Always weighed = Actual weight from invoice
4. **Missing weight on on-call invoice** = Flag as `needs_weight`

---

## Output Schema

### weight_tons
Extracted weight in tons as decimal:
- `2.45` - 2.45 tons
- `0.89` - 0.89 tons (less than 1 ton)
- `12.5` - 12.5 tons
- `None` - Weight not found on invoice

### weight_source
Source classification:
| Value | Description |
|-------|-------------|
| `actual` | Weight extracted from invoice |
| `calculated` | Weight derived from formula (recurring services) |
| `needs_weight` | On-call service missing weight on invoice |
| `needs_frequency` | Recurring service missing frequency for calculation |

---

## Common Weight Formats in Invoices

### Format 1: Decimal + TONS (Most Common)
```
"2.45 TONS"
"2.45 Tons"
"2.45 tons"
"2.45TONS"
```

**Pattern:**
```python
re.compile(r'(\d+\.?\d*)\s*TONS?', re.IGNORECASE)
```

### Format 2: Decimal + T (Abbreviated)
```
"2.45 T"
"2.45T"
"2.45 t"
```

**Pattern:**
```python
re.compile(r'(\d+\.?\d*)\s*T\b', re.IGNORECASE)
```

### Format 3: Weight in Pounds (Convert to Tons)
```
"4,900 LBS"
"4900 lbs"
"4,900 Pounds"
```

**Pattern:**
```python
re.compile(r'(\d{1,3}(?:,\d{3})*|\d+)\s*(?:LBS?|POUNDS?)', re.IGNORECASE)
# Conversion: tons = lbs / 2000
```

### Format 4: Net Weight Label
```
"Net Weight: 2.45 Tons"
"NET WT: 2.45T"
"Net Tons: 2.45"
```

**Pattern:**
```python
re.compile(r'NET\s*(?:WEIGHT|WT|TONS?)[:.]?\s*(\d+\.?\d*)\s*(?:TONS?|T)?', re.IGNORECASE)
```

### Format 5: Tonnage in Line Item Description
```
"30YD ROLL OFF - 2.45 TONS TRASH"
"40YD OPEN TOP HAUL - 3.2T C&D"
"COMPACTOR PULL 4.89 TONS"
```

**Pattern:**
```python
re.compile(r'(\d+\.?\d*)\s*(?:TONS?|T)\s+(?:TRASH|MSW|C&D|RECYCL)', re.IGNORECASE)
```

### Format 6: Disposal/Haul Charge with Weight
```
"Disposal Charge 2.45 Tons @ $45.00/Ton"
"Haul & Disposal - 3.2 T @ $52/T"
"TONNAGE CHARGE: 2.45 TONS"
```

**Pattern:**
```python
re.compile(r'(?:DISPOSAL|HAUL|TONNAGE)\s+(?:CHARGE)?[:\s-]*(\d+\.?\d*)\s*(?:TONS?|T)', re.IGNORECASE)
```

### Format 7: Weight Range (Take Higher Value)
```
"2.45 - 2.50 TONS"
"2.45-2.50T"
```

**Pattern:**
```python
re.compile(r'(\d+\.?\d*)\s*-\s*(\d+\.?\d*)\s*(?:TONS?|T)', re.IGNORECASE)
# Use the second (higher) value
```

### Format 8: Tare/Gross/Net Format
```
"Gross: 45,200 lbs  Tare: 15,400 lbs  Net: 29,800 lbs"
"GROSS 22.6T TARE 11.2T NET 11.4T"
```

**Pattern:**
```python
re.compile(r'NET[:.\s]*(\d+\.?\d*)\s*(?:TONS?|T|LBS?)', re.IGNORECASE)
# Always extract NET weight
```

---

## Architecture

### Dispatcher Pattern (matches line_item_extraction_module.py)

```python
def extract_weight(vendor: str, description: str, raw_ocr: str = None) -> Dict[str, Optional[float]]:
    """
    Extract weight from invoice for on-call services.

    Args:
        vendor: Vendor name for routing to vendor-specific patterns
        description: Line item/charge description
        raw_ocr: Full OCR text of invoice (for context search)

    Returns:
        {'weight_tons': float or None, 'weight_source': str}
    """
    vendor_lower = vendor.lower().strip()

    # Try vendor-specific extraction first
    if 'waste management' in vendor_lower or 'wm ' in vendor_lower:
        result = extract_weight_wm(description, raw_ocr)
    elif 'republic' in vendor_lower:
        result = extract_weight_republic(description, raw_ocr)
    elif 'waste connections' in vendor_lower:
        result = extract_weight_waste_connections(description, raw_ocr)
    # ... more vendors ...
    else:
        result = extract_weight_generic(description, raw_ocr)

    return result
```

### Generic Extraction Function

```python
# Ordered by specificity (most specific patterns first)
WEIGHT_PATTERNS = [
    # Net weight (most reliable)
    (re.compile(r'NET\s*(?:WEIGHT|WT|TONS?)[:.]?\s*(\d+\.?\d*)\s*(?:TONS?|T)?', re.I), 'tons'),

    # Tonnage charge format
    (re.compile(r'(?:DISPOSAL|TONNAGE)\s*(?:CHARGE)?[:\s-]*(\d+\.?\d*)\s*(?:TONS?|T)', re.I), 'tons'),

    # Decimal + TONS
    (re.compile(r'(\d+\.?\d*)\s*TONS?(?:\s|$|[,.])', re.I), 'tons'),

    # Decimal + T (standalone)
    (re.compile(r'(\d+\.\d+)\s*T\b', re.I), 'tons'),  # Require decimal to avoid false positives

    # Pounds (convert)
    (re.compile(r'(\d{1,3}(?:,\d{3})*|\d+)\s*(?:LBS?|POUNDS?)', re.I), 'lbs'),
]

def extract_weight_generic(description: str, raw_ocr: str = None) -> Dict:
    """Generic weight extraction using common patterns."""
    result = {'weight_tons': None, 'weight_source': 'needs_weight'}

    # Search in description first, then raw_ocr
    search_texts = [description]
    if raw_ocr:
        search_texts.append(raw_ocr)

    for text in search_texts:
        if not text:
            continue

        for pattern, unit in WEIGHT_PATTERNS:
            match = pattern.search(text)
            if match:
                weight = match.group(1).replace(',', '')
                weight = float(weight)

                # Convert lbs to tons if needed
                if unit == 'lbs':
                    weight = weight / 2000.0

                # Sanity check: weight should be reasonable (0.1 - 50 tons typical)
                if 0.01 <= weight <= 100:
                    result['weight_tons'] = round(weight, 3)
                    result['weight_source'] = 'actual'
                    return result

    return result
```

---

## Vendor-Specific Patterns

### Waste Management (WM)

**Invoice Format:**
```
Container: 30 YD OPEN TOP
Service Date: 01/15/2026
Tons: 2.450
Disposal Fee: $122.50
```

**Pattern:**
```python
WM_PATTERNS = {
    'tons_line': re.compile(r'Tons?[:.\s]*(\d+\.?\d*)', re.I),
    'disposal_fee': re.compile(r'Disposal.*?(\d+\.?\d*)\s*(?:TONS?|T)', re.I),
}
```

### Republic Services

**Invoice Format:**
```
1-30YD Open Top Container Haul
  Net Weight: 2.45 Tons
  Disposal @ $50.00/Ton: $122.50
```

**Pattern:**
```python
REPUBLIC_PATTERNS = {
    'net_weight': re.compile(r'Net\s*Weight[:.\s]*(\d+\.?\d*)\s*Tons?', re.I),
    'disposal_rate': re.compile(r'(\d+\.?\d*)\s*(?:Tons?|T)\s*@', re.I),
}
```

### Waste Connections

**Invoice Format:**
```
OPEN TOP 30YD HAUL - TRASH
QTY: 1  TONS: 2.450  RATE: $52.00/TON
```

**Pattern:**
```python
WC_PATTERNS = {
    'tons_field': re.compile(r'TONS[:.\s]*(\d+\.?\d*)', re.I),
    'inline': re.compile(r'(\d+\.?\d*)\s*TONS?\s+(?:RATE|@)', re.I),
}
```

### Athens Services

**Invoice Format:**
```
Roll Off Service - 30 Yard
Tonnage: 2.45
Disposal Charge: $98.00
```

**Pattern:**
```python
ATHENS_PATTERNS = {
    'tonnage_line': re.compile(r'Tonnage[:.\s]*(\d+\.?\d*)', re.I),
}
```

### Rumpke

**Invoice Format:**
```
30YD RO/HAUL-MSW
2.45 TONS @ $48.50/TON = $118.83
```

**Pattern:**
```python
RUMPKE_PATTERNS = {
    'tons_rate': re.compile(r'(\d+\.?\d*)\s*TONS?\s*@', re.I),
}
```

---

## Normalization Rules

### Weight Normalization

```python
def normalize_weight(value: float, unit: str) -> float:
    """
    Normalize weight to tons.

    Args:
        value: Numeric weight value
        unit: 'tons', 'lbs', 'kg'

    Returns:
        Weight in tons (rounded to 3 decimal places)
    """
    if unit == 'lbs':
        return round(value / 2000.0, 3)
    elif unit == 'kg':
        return round(value / 907.185, 3)  # kg to tons
    else:
        return round(value, 3)
```

### Sanity Checks

```python
def validate_weight(weight: float, equipment_type: str) -> bool:
    """
    Validate extracted weight is reasonable for equipment type.

    Typical ranges:
    - Open Top 20YD: 1-8 tons
    - Open Top 30YD: 2-12 tons
    - Open Top 40YD: 3-15 tons
    - Compactor: 2-20 tons (higher density)
    """
    if weight <= 0:
        return False
    if weight > 50:  # Unreasonably high
        return False
    if weight < 0.1:  # Unreasonably low for roll-off
        return False
    return True
```

---

## Integration with NG Report Pipeline

### Current Pipeline Flow (Step 3)

```
Step 3: WeightCalculator
├── Load density factors from Azure SQL
├── For each service:
│   ├── If Front Load/Toter → Calculate weight
│   └── If Open Top/Compactor → Mark as "needs actual weight"
└── Output: weight_calculated_tons, weight_source
```

### Updated Pipeline Flow

```
Step 3: WeightCalculator
├── Load density factors from Azure SQL
├── For each service:
│   ├── If Front Load/Toter → Calculate weight
│   └── If Open Top/Compactor:
│       ├── Call extract_weight(vendor, description, raw_ocr)
│       ├── If weight found → weight_source = "actual"
│       └── If not found → weight_source = "needs_weight"
└── Output: weight_tons, weight_source
```

### Code Integration

```python
# In weight_calculator.py, update calculate_weights_dataframe():

from parsing_engines.line_items.weight_extraction_module import extract_weight

def calculate_weights_dataframe(self, df: pd.DataFrame) -> pd.DataFrame:
    # ... existing code ...

    for idx in df.index:
        row = df.loc[idx]
        equipment = row.get("equipment_type", "")

        if self.is_calculated_equipment(equipment):
            # Recurring service - calculate weight
            weight = self.calculate_weight_tons(...)
            # ... existing logic ...
        else:
            # On-call service - extract actual weight from invoice
            weight_result = extract_weight(
                vendor=row.get("vendor_clean", ""),
                description=row.get("item_description", ""),
                raw_ocr=row.get("raw_ocr_text", None)  # If available
            )

            if weight_result['weight_tons'] is not None:
                df.at[idx, "weight_tons"] = weight_result['weight_tons']
                df.at[idx, "weight_source"] = "actual"
            else:
                df.at[idx, "weight_source"] = "needs_weight"
```

---

## Workflow: Adding a New Vendor

### Step 1: Collect Sample Invoices

Get 5-10 sample invoices from the vendor with Open Top/Compactor hauls:
```python
import pandas as pd

# From OCR data
ocr = pd.read_csv('ocr_chunk_1.csv')
vendor_ocr = ocr[ocr['vendor'].str.contains('New Vendor', case=False, na=False)]
samples = vendor_ocr[['raw_text', 'file_name']].head(10)
for _, row in samples.iterrows():
    print(f"=== {row['file_name']} ===")
    print(row['raw_text'][:500])
```

### Step 2: Identify Weight Patterns

Look for:
- Where does weight appear? (line item, summary, separate line)
- What format? (X.XX TONS, X.XX T, X,XXX LBS)
- Is there a "Net Weight" label?
- Is weight part of a rate calculation? (X.XX TONS @ $XX/TON)

### Step 3: Create Vendor Patterns

```python
NEW_VENDOR_PATTERNS = {
    'primary': re.compile(r'...'),  # Most common format
    'alternate': re.compile(r'...'),  # Backup pattern
}

def extract_weight_new_vendor(description: str, raw_ocr: str = None) -> Dict:
    """Extract weight from New Vendor invoices."""
    result = {'weight_tons': None, 'weight_source': 'needs_weight'}

    # Try description first
    match = NEW_VENDOR_PATTERNS['primary'].search(description)
    if match:
        result['weight_tons'] = float(match.group(1))
        result['weight_source'] = 'actual'
        return result

    # Try raw OCR
    if raw_ocr:
        match = NEW_VENDOR_PATTERNS['primary'].search(raw_ocr)
        if match:
            result['weight_tons'] = float(match.group(1))
            result['weight_source'] = 'actual'
            return result

    return result
```

### Step 4: Add to Dispatcher

```python
# In extract_weight():
elif 'new vendor' in vendor_lower:
    return extract_weight_new_vendor(description, raw_ocr)
```

### Step 5: Test

```python
test_cases = [
    ('New Vendor', '30YD OPEN TOP HAUL - 2.45 TONS'),
    ('New Vendor', 'COMPACTOR SERVICE\nNet Weight: 4.89 Tons'),
]

for vendor, desc in test_cases:
    result = extract_weight(vendor, desc)
    print(f"Input: {desc[:50]}...")
    print(f"Output: {result}")
```

---

## Common Issues and Fixes

### Issue 1: False Positives from Container Size

**Symptom:** Extracting "30" from "30YD OPEN TOP" as weight

**Fix:** Require decimal point or "TONS/T" suffix for weight patterns
```python
# Bad: matches container size
re.compile(r'(\d+)\s*T')

# Good: requires decimal or explicit TONS
re.compile(r'(\d+\.\d+)\s*T\b')  # Decimal required
re.compile(r'(\d+\.?\d*)\s*TONS')  # TONS spelled out
```

### Issue 2: Extracting Tare Instead of Net

**Symptom:** Wrong weight from Gross/Tare/Net format

**Fix:** Explicitly look for NET
```python
# Look for NET weight specifically
re.compile(r'NET[:.\s]*(\d+\.?\d*)\s*(?:TONS?|T|LBS?)', re.I)
```

### Issue 3: Multiple Weights on Invoice

**Symptom:** Multiple hauls on one invoice, wrong weight extracted

**Fix:** Associate weight with line item, not just invoice
```python
# Search within line item context, not entire OCR
line_pattern = re.compile(r'OPEN TOP.*?(\d+\.?\d*)\s*TONS?', re.I | re.DOTALL)
```

### Issue 4: Weight in Pounds Not Converted

**Symptom:** Large weight values (e.g., 4900 instead of 2.45)

**Fix:** Detect unit and convert
```python
if 'LBS' in text.upper() or 'POUNDS' in text.upper():
    weight = weight / 2000.0
```

---

## Testing Commands

```python
from weight_extraction_module import extract_weight

# Test single extraction
result = extract_weight('Waste Management', '30YD OPEN TOP - 2.45 TONS MSW')
print(result)
# {'weight_tons': 2.45, 'weight_source': 'actual'}

# Test with raw OCR
raw_ocr = """
INVOICE #12345
30 YARD OPEN TOP CONTAINER
SERVICE DATE: 01/15/2026
NET WEIGHT: 2.450 TONS
DISPOSAL @ $50.00/TON = $122.50
"""
result = extract_weight('Republic Services', 'Open Top Haul', raw_ocr)
print(result)
# {'weight_tons': 2.45, 'weight_source': 'actual'}

# Test missing weight
result = extract_weight('Unknown Vendor', 'CONTAINER RENTAL')
print(result)
# {'weight_tons': None, 'weight_source': 'needs_weight'}
```

---

## Validation Report Integration

When weight extraction is complete, update validation to report:

```python
# In validation_report.py
def validate_weights(df):
    total = len(df)
    calculated = len(df[df['weight_source'] == 'calculated'])
    actual = len(df[df['weight_source'] == 'actual'])
    needs_weight = len(df[df['weight_source'] == 'needs_weight'])

    print(f"Weight Coverage:")
    print(f"  Calculated (recurring): {calculated} ({calculated/total*100:.1f}%)")
    print(f"  Actual (from invoice): {actual} ({actual/total*100:.1f}%)")
    print(f"  Needs weight: {needs_weight} ({needs_weight/total*100:.1f}%)")

    if needs_weight > 0:
        print(f"\nServices missing weight:")
        missing = df[df['weight_source'] == 'needs_weight']
        for _, row in missing.head(10).iterrows():
            print(f"  - {row['vendor_clean']}: {row['item_description'][:50]}")
```

---

## Priority Vendors for Weight Extraction

Based on NG Report data (410 on-call services), prioritize vendors by volume:

| Vendor | On-Call Services | Priority |
|--------|------------------|----------|
| Waste Management | ~80 | High |
| Republic Services | ~65 | High |
| Waste Connections | ~55 | High |
| Athens Services | ~40 | High |
| Rumpke | ~30 | Medium |
| Cockey's Enterprises | ~25 | Medium |
| GFL | ~20 | Medium |
| Other (15+ vendors) | ~95 | Low (generic) |

---

## Related Modules

| Module | Dependency |
|--------|------------|
| `01_vendor_detection` | Provides vendor name for routing |
| `03_line_item_equipment_material` | Identifies equipment type to determine if weight extraction needed |
| `ocr_pipeline.py` (ng-report) | Provides raw OCR text for extraction |
| `weight_calculator.py` (ng-report) | Integrates extracted weights |

---

## Version History

| Version | Changes |
|---------|---------|
| 1.0 | Initial document - patterns and architecture defined |
| Planned | Vendor-specific implementations, integration with pipeline |

---

## Contact & Ownership

**Owner:** Shane @ Wasteology
**Module:** Invoice Processing System - Weight Extraction
**Created:** February 2026
**Reference:** Weight Instructions.md
