# Line Item Extraction (Equipment/Material) - Claude Instructions

## Purpose

This document provides all context needed for Claude to efficiently update line item extraction patterns for equipment size, equipment type, and material fields. Load this document whenever you need to add new vendors, fix extraction failures, or improve parsing accuracy.

---

## Module Overview

**File:** `/mnt/project/line_item_extraction_module.py`  
**Function:** Extract equipment_size, equipment_type, and material from line item descriptions  
**Configured Vendors:** 15  
**Output Fields:** `equipment_size`, `equipment_type`, `material`

---

## Data Files Reference

| File | Purpose | Key Columns |
|------|---------|-------------|
| `billing_chunk_*.csv` (1-6) | Billing records with charge descriptions | `charge_description`, `equipment_type`, `material` |
| `ocr_chunk_*.csv` (1-7) | Raw OCR for parsing line items | `raw_text` |
| `services_chunk_*.csv` (1-2) | Service records with equipment info | `equipment_type`, `material`, `container_type` |

---

## Output Schema

### equipment_size
Normalized container size with unit:
- `"8 YD"` - 8 cubic yard container
- `"30 YD"` - 30 cubic yard roll-off
- `"96 GAL"` - 96 gallon cart/toter
- `None` - Not determinable from description

### equipment_type
Normalized equipment category:
| Value | Description |
|-------|-------------|
| `FRONT LOAD` | Standard dumpster (2-8 YD) |
| `ROLL OFF` | Open top container (10-40 YD) |
| `COMPACTOR` | Compacting container |
| `CART` | Wheeled cart/toter (typically gallon-sized) |
| `None` | Not determinable |

### material
Normalized waste stream:
| Value | Description |
|-------|-------------|
| `MSW` | Municipal Solid Waste / Trash |
| `RECYCLING` | Mixed recycling |
| `OCC` | Old Corrugated Cardboard |
| `CARDBOARD` | Cardboard (alternate) |
| `C&D` | Construction & Demolition |
| `METAL` | Scrap metal |
| `ORGANICS` | Food waste/organics |
| `None` | Not determinable |

---

## Architecture

### Dispatcher Pattern

```python
def extract_line_item_fields(vendor: str, description: str) -> Dict[str, Optional[str]]:
    """Routes to vendor-specific extraction function."""
    vendor_lower = vendor.lower().strip()
    
    if 'universal waste' in vendor_lower:
        return extract_universal_waste(description)
    elif 'rumpke' in vendor_lower:
        return extract_rumpke(description)
    # ... more vendors ...
    else:
        return {'equipment_size': None, 'equipment_type': None, 'material': None}
```

### Vendor Extraction Pattern

Each vendor has:
1. **Pattern dictionary** - Compiled regex patterns
2. **Extraction function** - Logic to apply patterns and normalize output

```python
VENDOR_PATTERNS = {
    'equipment_size': re.compile(r'(\d+)\s*YD', re.IGNORECASE),
    'equipment_type': re.compile(r'(FRONT\s*LOAD|ROLL\s*OFF)', re.IGNORECASE),
    'material': re.compile(r'(TRASH|RECYCL\w*|MSW|OCC)', re.IGNORECASE),
}

def extract_vendor(description: str) -> Dict[str, Optional[str]]:
    result = {'equipment_size': None, 'equipment_type': None, 'material': None}
    
    size_match = VENDOR_PATTERNS['equipment_size'].search(description)
    if size_match:
        result['equipment_size'] = f"{size_match.group(1)} YD"
    
    # ... more extraction logic ...
    return result
```

---

## Common Description Formats

### Format 1: Size + Type + Material (Inline)
```
"8 YD FRONT LOAD TRASH"
"6YD FL Recycling"
"30YD ROLL OFF - SCRAP METAL"
```

**Pattern:**
```python
re.compile(r'(\d+)\s*YD\s+(FRONT\s*LOAD|FL|ROLL\s*OFF|RO)\s+[-]?\s*(TRASH|RECYCL\w*|MSW)', re.I)
```

### Format 2: Coded Format (Abbreviations)
```
"8YD FL/MONTH-MSW"          # Rumpke
"FL-Comm-Trash-08yd"        # Cockey's
"COMM FL WASTE PERM 8YD"    # GFL
```

**Pattern:**
```python
# Rumpke: 8YD FL/MONTH-MSW
re.compile(r'(\d+)YD\s+FL/(?:MONTH|EXTRA)-(\w+)', re.I)

# Cockey's: FL-Comm-Material-XXyd
re.compile(r'FL-Comm-(\w+)-(\d+)yd', re.I)
```

### Format 3: Equipment Code + Description
```
"30YDRO 30 YARD OPEN TOP"   # Standard Waste
"40YDCO 40 YARD COMPACTOR"
```

**Pattern:**
```python
re.compile(r'(\d+)YD(RO|CO|REC)', re.I)  # Code: 30YDRO
re.compile(r'(\d+)\s*YARD\s+(OPEN\s*TOP|COMPACTOR)', re.I)  # Description
```

### Format 4: Service Description Format
```
"1 Waste Container 2 Cu Yd, 1 Lift Per Week"    # Republic
"FRONTLOAD 4 YD - SOLID WASTE SERVICE"          # Waste Pro
"Pickup 1 Yards Trash DMP Weekly x1"            # WM
```

**Pattern:**
```python
# Republic
re.compile(r'(Waste|Recycle)\s+Container\s+(\d+)\s*Cu\s*Yd', re.I)

# Waste Pro  
re.compile(r'FRONTLOAD\s+(\d+)\s*YD\s*-\s*(SOLID\s*WASTE|RECYCLE)', re.I)
```

### Format 5: Charge-Based (Material in Fee Description)
```
"Disposal Charge - Trash"       # Hamilton Alliance
"Haul Fees Cardboard"           # Anytime Waste
"DISPOSAL-I/C OCC"              # Casella
```

**Pattern:**
```python
re.compile(r'(?:Disposal|Haul)\s+(?:Charge|Fees?)\s*-?\s*(Trash|OCC|Cardboard)', re.I)
```

---

## Configured Vendors

| Vendor | Size Format | Type Format | Material Format |
|--------|-------------|-------------|-----------------|
| Universal Waste | `6YD` | `FL` | `Trash` |
| Active Waste | `8 YD`, `95 GALLON` | `FRONT LOAD` | `TRASH`, `RECYCLE` |
| Boren Brothers | `8 YD`, `30YD` | `FRONT LOAD`, `ROLL OFF` | `TRASH`, `SCRAP METAL` |
| Rumpke | `8YD` | `FL`, `RO` | `-MSW`, `-CRDBD` |
| Cockey's | `08yd`, `95gl` | `FL-`, `RL-`, `RO` | `-Recycling-`, `-Trash-` |
| Robinson Waste | `3YD`, `3.00YD` | `Front Load` | `Trash`, `Recycl` |
| Standard Waste | `30YDRO`, `40YDCO` | Code-based | `TONS-MSW` |
| Hamilton Alliance | `30yd`, `40yd` | `Open Top`, `Compactor` | `- Trash` |
| Casella | `8YD`, `96GL` | `FL`, `CART`, `STR BOX` | `TRASH`, `ZERO SO` |
| Waste Pro | `4 YD`, `96 Gal` | `FRONTLOAD`, `Toter` | `SOLID WASTE` |
| GFL | `8YD`, `96 GAL` | `FL`, `FRONT LOAD` | `WASTE`, `MSW` |
| Waste Connections | `8 Yd`, `95 GL` | Implied by size | `REC`, `CONT` |
| Anytime Waste | `20 YD` | `Roll Off` | `Trash`, `Cardboard` |
| Waste Management | `1 Yards`, `96 Gallons` | `DMP`, `TOT` | `Trash` |
| Republic Services | `2 Cu Yd`, `95 Gal` | `Container`, `Cart` | `Waste`, `Recycle` |

---

## Normalization Rules

### Size Normalization
```python
# Always format as: "{number} {unit}"
"8YD" → "8 YD"
"08yd" → "8 YD"        # Remove leading zeros
"8 Yd" → "8 YD"        # Uppercase unit
"95gl" → "95 GAL"
"2 Cu Yd" → "2 YD"     # Normalize "Cu Yd" to "YD"
```

### Equipment Type Normalization
```python
type_map = {
    'FL': 'FRONT LOAD',
    'FRONT LOAD': 'FRONT LOAD',
    'RO': 'ROLL OFF',
    'ROLL OFF': 'ROLL OFF',
    'OPEN TOP': 'ROLL OFF',
    'CO': 'COMPACTOR',
    'STR BOX': 'COMPACTOR',
    'CART': 'CART',
    'TOTER': 'CART',
    'TOT': 'CART',
}
```

### Material Normalization
```python
material_map = {
    'TRASH': 'MSW',
    'SOLID WASTE': 'MSW',
    'MSW': 'MSW',
    'RECYCLING': 'RECYCLING',
    'RECYCLE': 'RECYCLING',
    'REC': 'RECYCLING',
    'ZERO SO': 'RECYCLING',      # Casella's "Zero Sort"
    'CRDBD': 'CARDBOARD',
    'OCC': 'OCC',
    'CARDBOARD': 'CARDBOARD',
    'C&D': 'C&D',
    'SCRAP METAL': 'METAL',
    'STEEL': 'METAL',
}
```

---

## Workflow: Adding a New Vendor

### Step 1: Collect Sample Descriptions

Get 10-20 sample line item descriptions from the vendor:
```python
import pandas as pd

billing = pd.read_csv('billing_chunk_1.csv')
vendor_data = billing[billing['vendor_name'].str.contains('New Vendor', case=False, na=False)]
samples = vendor_data['charge_description'].dropna().unique()[:20]
for s in samples:
    print(s)
```

### Step 2: Identify Patterns

Analyze samples to find:
- Where does size appear? (beginning, middle, end)
- What abbreviations are used? (FL, RO, YD, CY)
- How is material indicated? (inline, suffix, separate)

### Step 3: Create Patterns Dictionary

```python
NEW_VENDOR_PATTERNS = {
    # Document each pattern with examples
    'equipment_size': re.compile(r'(\d+)\s*YD', re.IGNORECASE),  # "8 YD", "30YD"
    'equipment_type': re.compile(r'(FRONT\s*LOAD|ROLL\s*OFF)', re.IGNORECASE),
    'material': re.compile(r'(TRASH|RECYCL\w*|MSW)', re.IGNORECASE),
}
```

### Step 4: Create Extraction Function

```python
def extract_new_vendor(description: str) -> Dict[str, Optional[str]]:
    """
    Extract fields from New Vendor line item description.
    
    Examples:
        "8 YD FRONT LOAD TRASH" → size=8 YD, type=FRONT LOAD, material=MSW
        "30YD ROLL OFF - C&D" → size=30 YD, type=ROLL OFF, material=C&D
    """
    result = {
        'equipment_size': None,
        'equipment_type': None,
        'material': None,
    }
    
    # Size extraction
    size_match = NEW_VENDOR_PATTERNS['equipment_size'].search(description)
    if size_match:
        result['equipment_size'] = f"{size_match.group(1)} YD"
    
    # Type extraction
    type_match = NEW_VENDOR_PATTERNS['equipment_type'].search(description)
    if type_match:
        result['equipment_type'] = type_match.group(1).upper().replace('  ', ' ')
    
    # Material extraction with normalization
    mat_match = NEW_VENDOR_PATTERNS['material'].search(description)
    if mat_match:
        mat = mat_match.group(1).upper()
        if mat == 'TRASH':
            mat = 'MSW'
        elif mat.startswith('RECYCL'):
            mat = 'RECYCLING'
        result['material'] = mat
    
    return result
```

### Step 5: Add to Dispatcher

```python
# In extract_line_item_fields():
elif 'new vendor' in vendor_lower:
    return extract_new_vendor(description)
```

### Step 6: Test

```python
test_cases = [
    ('New Vendor', '8 YD FRONT LOAD TRASH'),
    ('New Vendor', '30YD ROLL OFF - C&D'),
    ('New Vendor', '96 GAL CART RECYCLING'),
]

for vendor, desc in test_cases:
    result = extract_line_item_fields(vendor, desc)
    print(f"Input: {desc}")
    print(f"Output: {result}")
```

---

## Common Issues and Fixes

### Issue 1: Size Not Extracted

**Symptom:** `equipment_size` returns None

**Common Causes:**
- Different unit format: `CY` vs `YD`, `Gallon` vs `GAL`
- Space variations: `8YD` vs `8 YD` vs `8-YD`
- Leading zeros: `08yd`

**Fix:**
```python
# Make pattern flexible
re.compile(r'(\d+)\s*(?:YD|YARD|CY|Cu\s*Yd)', re.I)
```

### Issue 2: Wrong Equipment Type

**Symptom:** Front load detected as roll-off or vice versa

**Cause:** Pattern order or overlapping patterns

**Fix:** Check patterns in order of specificity
```python
# Check more specific pattern first
if 'FRONT LOAD' in description.upper() or ' FL ' in description.upper():
    result['equipment_type'] = 'FRONT LOAD'
elif 'ROLL OFF' in description.upper() or ' RO ' in description.upper():
    result['equipment_type'] = 'ROLL OFF'
```

### Issue 3: Material Normalization

**Symptom:** Material values inconsistent

**Fix:** Always normalize at extraction time
```python
# Normalize common variants
mat = match.group(1).upper()
if mat in ('TRASH', 'SOLID WASTE', 'REFUSE'):
    mat = 'MSW'
elif mat.startswith('RECYCL') or mat in ('REC', 'ZERO SO'):
    mat = 'RECYCLING'
result['material'] = mat
```

### Issue 4: Gallon vs Yard Confusion

**Symptom:** Cart sizes extracted as yard sizes

**Fix:** Check for gallon indicators first
```python
# Check gallon first (more specific)
gal_match = re.search(r'(\d+)\s*(?:GAL|GALLON|GL)', description, re.I)
if gal_match:
    result['equipment_size'] = f"{gal_match.group(1)} GAL"
    result['equipment_type'] = 'CART'
    return result

# Then check yard
yd_match = re.search(r'(\d+)\s*YD', description, re.I)
```

---

## Testing Commands

```python
from line_item_extraction_module import extract_line_item_fields

# Test single extraction
result = extract_line_item_fields('Rumpke', '8YD FL/MONTH-MSW')
print(result)
# {'equipment_size': '8 YD', 'equipment_type': 'FRONT LOAD', 'material': 'MSW'}

# Test all vendors
test_cases = [
    ('Universal Waste', '6YD FL Trash'),
    ('Rumpke', '8YD FL/MONTH-MSW'),
    ('Casella', '8YD FL WEEKLY TRASH'),
    ('Republic Services', '1 Waste Container 2 Cu Yd'),
]

for vendor, desc in test_cases:
    r = extract_line_item_fields(vendor, desc)
    print(f"{vendor}: {r}")
```

---

## Related Modules

| Module | Dependency |
|--------|------------|
| `01_vendor_detection` | Provides vendor name for routing |
| `02_account_extraction` | Uses vendor for context |
| `04_line_items_charge_description` | Handles charge type parsing |

---

## Version History

| Version | Changes |
|---------|---------|
| Current | 15 vendors, equipment/material extraction |
| Planned | Additional vendors, charge categorization |

---

## Contact & Ownership

**Owner:** Shane @ Wasteology
**Module:** Invoice Processing System - Line Item Extraction (Equipment/Material)
**Last Updated:** January 2026
