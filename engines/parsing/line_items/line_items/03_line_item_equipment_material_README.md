# 03 Line Item Extraction - Equipment & Material

## Overview

The Line Item Extraction Module (Equipment/Material) is the third stage of Wasteology's invoice processing pipeline. After identifying the vendor and extracting the account number, this module parses line item descriptions to extract structured equipment and material information. This enables accurate service matching and billing reconciliation.

---

# Business Documentation

## What It Does

Invoice line items contain descriptions like "8 YD FRONT LOAD TRASH" or "30YD ROLL OFF - SCRAP METAL". This module parses these descriptions to extract three key pieces of information:

1. **Equipment Size** - How big is the container? (e.g., "8 YD", "30 YD", "96 GAL")
2. **Equipment Type** - What kind of container? (e.g., Front Load, Roll Off, Cart)
3. **Material** - What waste stream? (e.g., Trash/MSW, Recycling, Cardboard)

**Example:**
```
Input:  "8 YD FRONT LOAD TRASH W/ LOCK BAR"
Output: 
  - equipment_size: "8 YD"
  - equipment_type: "FRONT LOAD"
  - material: "MSW"
```

## Why It Matters

1. **Service Matching:** We need to match invoice charges to the correct service. A "6 YD recycling" charge shouldn't match to an "8 YD trash" service.

2. **Rate Validation:** Different equipment sizes and materials have different rates. Accurate extraction ensures we validate against the correct contracted rate.

3. **Client Reporting:** Customers expect detailed breakdowns by equipment type and material stream.

## Equipment Types Explained

| Type | Description | Typical Sizes |
|------|-------------|---------------|
| **Front Load** | Standard commercial dumpster, lifted from front | 2-8 cubic yards |
| **Roll Off** | Large open-top container, rolled onto truck | 10-40 cubic yards |
| **Compactor** | Self-compacting container | 20-40 cubic yards |
| **Cart** | Wheeled residential-style container | 35-96 gallons |

## Material Types Explained

| Material | Description | Common Aliases |
|----------|-------------|----------------|
| **MSW** | Municipal Solid Waste (regular trash) | Trash, Solid Waste, Refuse |
| **Recycling** | Mixed recyclables | Single Stream, Zero Sort |
| **OCC** | Old Corrugated Cardboard | Cardboard, CRDBD |
| **C&D** | Construction & Demolition debris | Concrete, Demo |
| **Metal** | Scrap metal | Steel, Scrap Metal |
| **Organics** | Food waste, compostables | Food Waste |

## Current Status

| Metric | Value |
|--------|-------|
| **Configured Vendors** | 15 |
| **Major Vendors Covered** | Waste Connections, Republic, WM, GFL, Rumpke |
| **Output Fields** | equipment_size, equipment_type, material |

## Configured Vendors

The following vendors have custom extraction logic:

1. Universal Waste
2. Active Waste
3. Boren Brothers
4. Rumpke
5. Cockey's Enterprises
6. Robinson Waste
7. Standard Waste
8. Hamilton Alliance
9. Casella
10. Waste Pro
11. GFL
12. Waste Connections
13. Anytime Waste
14. Waste Management
15. Republic Services

## When Updates Are Needed

- **New vendor:** High-volume vendor not yet configured
- **Format change:** Vendor updates their line item descriptions
- **Missing extractions:** Equipment or material returning None for known formats

---

# Technical Documentation

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                   LINE ITEM EXTRACTION PIPELINE                  │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │  Input: vendor_name + line_item_description              │   │
│  │                                                          │   │
│  │  "Rumpke" + "8YD FL/MONTH-MSW"                          │   │
│  └──────────────────────────────────────────────────────────┘   │
│                              │                                   │
│                              ▼                                   │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │              extract_line_item_fields()                   │   │
│  │                                                          │   │
│  │  ┌─────────────────────────────────────────────────┐    │   │
│  │  │           VENDOR DISPATCHER                      │    │   │
│  │  │                                                  │    │   │
│  │  │  if 'rumpke' in vendor:                         │    │   │
│  │  │      return extract_rumpke(description)         │    │   │
│  │  │  elif 'casella' in vendor:                      │    │   │
│  │  │      return extract_casella(description)        │    │   │
│  │  │  ...                                            │    │   │
│  │  └─────────────────────────────────────────────────┘    │   │
│  │                              │                           │   │
│  │                              ▼                           │   │
│  │  ┌─────────────────────────────────────────────────┐    │   │
│  │  │     VENDOR-SPECIFIC EXTRACTION FUNCTION          │    │   │
│  │  │                                                  │    │   │
│  │  │  RUMPKE_PATTERNS = {                            │    │   │
│  │  │    'equipment_size': r'(\d+)\s*YD',             │    │   │
│  │  │    'equipment_type_fl': r'\d+\s*YD\s*(FL)',     │    │   │
│  │  │    'material_fl': r'FL/(?:MONTH)-(\w+)',        │    │   │
│  │  │  }                                              │    │   │
│  │  │                                                  │    │   │
│  │  │  → Apply patterns                               │    │   │
│  │  │  → Normalize values                             │    │   │
│  │  │  → Return structured result                     │    │   │
│  │  └─────────────────────────────────────────────────┘    │   │
│  └──────────────────────────────────────────────────────────┘   │
│                              │                                   │
│                              ▼                                   │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │  Output: {                                               │   │
│  │    'equipment_size': '8 YD',                             │   │
│  │    'equipment_type': 'FRONT LOAD',                       │   │
│  │    'material': 'MSW'                                     │   │
│  │  }                                                       │   │
│  └──────────────────────────────────────────────────────────┘   │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

## File Structure

```
/mnt/project/
├── line_item_extraction_module.py   # Main module (this component)
├── billing_chunk_*.csv              # Billing records with charge descriptions
├── services_chunk_*.csv             # Service records with equipment info
└── ocr_chunk_*.csv                  # Raw OCR (for line-level parsing)
```

## Module Structure

```python
# Pattern dictionaries per vendor
VENDOR_PATTERNS = {
    'equipment_size': re.compile(r'...'),
    'equipment_type': re.compile(r'...'),
    'material': re.compile(r'...'),
}

# Vendor-specific extraction function
def extract_vendor(description: str) -> Dict[str, Optional[str]]:
    result = {'equipment_size': None, 'equipment_type': None, 'material': None}
    # Apply patterns, normalize, return
    return result

# Main dispatcher
def extract_line_item_fields(vendor: str, description: str) -> Dict[str, Optional[str]]:
    if 'vendor' in vendor.lower():
        return extract_vendor(description)
    # ... more vendors
    return {'equipment_size': None, 'equipment_type': None, 'material': None}
```

## API Reference

### extract_line_item_fields(vendor, description)

Main extraction function.

**Parameters:**
- `vendor` (str): Vendor name (from vendor_detection_module)
- `description` (str): Line item description from invoice

**Returns:**
```python
{
    'equipment_size': str or None,    # "8 YD", "96 GAL"
    'equipment_type': str or None,    # "FRONT LOAD", "ROLL OFF", "CART"
    'material': str or None           # "MSW", "RECYCLING", "OCC"
}
```

**Example:**
```python
from line_item_extraction_module import extract_line_item_fields

result = extract_line_item_fields('Rumpke', '8YD FL/MONTH-MSW')
# Returns: {'equipment_size': '8 YD', 'equipment_type': 'FRONT LOAD', 'material': 'MSW'}
```

## Vendor-Specific Patterns

### Rumpke
```
Format: {size}YD {type}/{frequency}-{material}
Examples:
  "8YD FL/MONTH-MSW"     → 8 YD, FRONT LOAD, MSW
  "20YD RO/LOAD-C&D"     → 20 YD, ROLL OFF, C&D
  "RO DISP/TON-STEEL"    → None, ROLL OFF, METAL
```

### Casella
```
Format: {size}YD {type} {frequency} {material}
Examples:
  "8YD FL WEEKLY TRASH"     → 8 YD, FRONT LOAD, MSW
  "96GL CART EOW ZERO SO"   → 96 GAL, CART, RECYCLING
  "40YD STR BOX D&R OCC"    → 40 YD, COMPACTOR, OCC
```

### Cockey's Enterprises
```
Format: {type}-Comm-{material}-{size}
Examples:
  "FL-Comm-Recycling-08yd"  → 8 YD, FRONT LOAD, RECYCLING
  "RL-Comm-Trash-95gl"      → 95 GAL, CART, MSW
  "RO Haul Charge - Open Top" → None, ROLL OFF, None
```

### Republic Services
```
Format: {count} {material} {type} {size} {unit}
Examples:
  "1 Waste Container 2 Cu Yd"    → 2 YD, FRONT LOAD, MSW
  "1 Recycle Cart 95 Gal"        → 95 GAL, CART, RECYCLING
  "1 Waste Compactor 40 Cu Yd"   → 40 YD, COMPACTOR, MSW
```

### Waste Management
```
Format: Pickup {size} {unit} {material} {type_code}
Examples:
  "Pickup 1 Yards Trash DMP Weekly"    → 1 YD, FRONT LOAD, MSW
  "Pickup 96 Gallons Trash TOT Weekly" → 96 GAL, CART, MSW
```

## Normalization Standards

### Size Normalization
All sizes are normalized to `"{number} {UNIT}"` format:

| Input | Output |
|-------|--------|
| `8YD` | `8 YD` |
| `08yd` | `8 YD` |
| `8 Yd` | `8 YD` |
| `2 Cu Yd` | `2 YD` |
| `95gl` | `95 GAL` |
| `96 Gallon` | `96 GAL` |

### Type Normalization
All types map to one of four standard values:

| Input Variants | Normalized Output |
|----------------|-------------------|
| FL, FRONT LOAD, FEL | `FRONT LOAD` |
| RO, ROLL OFF, OPEN TOP | `ROLL OFF` |
| CO, COMPACTOR, STR BOX | `COMPACTOR` |
| CART, TOTER, TOT | `CART` |

### Material Normalization
All materials map to standard values:

| Input Variants | Normalized Output |
|----------------|-------------------|
| TRASH, SOLID WASTE, REFUSE | `MSW` |
| RECYCLING, RECYCLE, REC, ZERO SO | `RECYCLING` |
| CARDBOARD, CRDBD | `CARDBOARD` |
| OCC | `OCC` |
| C&D, CONCRETE | `C&D` |
| SCRAP METAL, STEEL | `METAL` |

## Testing

### Unit Tests
```python
def test_rumpke():
    test_cases = [
        ('8YD FL/MONTH-MSW', {'equipment_size': '8 YD', 'equipment_type': 'FRONT LOAD', 'material': 'MSW'}),
        ('20YD RO/LOAD-C&D', {'equipment_size': '20 YD', 'equipment_type': 'ROLL OFF', 'material': 'C&D'}),
        ('FUEL SURCHARGE FL', {'equipment_size': None, 'equipment_type': None, 'material': None}),
    ]
    for desc, expected in test_cases:
        result = extract_rumpke(desc)
        assert result == expected, f"Failed: {desc}"
```

### Run All Tests
```bash
python3 line_item_extraction_module.py
```

The module includes a `__main__` block with comprehensive test cases for all vendors.

### Bulk Validation
```python
import pandas as pd
from line_item_extraction_module import extract_line_item_fields

billing = pd.read_csv('billing_chunk_1.csv')

# Test extraction for specific vendor
vendor = 'Rumpke'
vendor_data = billing[billing['vendor_name'].str.contains(vendor, case=False, na=False)]

for _, row in vendor_data.head(20).iterrows():
    desc = row['charge_description']
    result = extract_line_item_fields(vendor, desc)
    print(f"{desc[:40]:<40} → {result}")
```

## Troubleshooting

| Symptom | Likely Cause | Solution |
|---------|--------------|----------|
| All fields None | Vendor not configured | Add vendor to dispatcher |
| Size None | Format mismatch | Add pattern for size format |
| Wrong type | Pattern too broad | Make type pattern more specific |
| Material None | Material in unexpected position | Add alternate material pattern |
| Wrong material | Normalization missing | Add to material_map |

## Performance Notes

- Patterns are pre-compiled (`re.compile`) for efficiency
- Each vendor function does early returns on first match
- Normalization happens at extraction time (no post-processing needed)

## Maintenance

### Adding a New Vendor

1. Collect 15-20 sample descriptions
2. Identify size/type/material patterns
3. Create `VENDOR_PATTERNS` dictionary
4. Create `extract_vendor()` function
5. Add to dispatcher in `extract_line_item_fields()`
6. Add test cases to `__main__` block
7. Run tests to validate

### Updating Existing Vendor

1. Identify failing descriptions
2. Add new patterns to handle variants
3. Update normalization if needed
4. Add test cases for new patterns
5. Verify existing tests still pass

---

## Related Documentation

- `03_line_item_equipment_material_INSTRUCTIONS.md` - Claude instructions for updates
- `01_vendor_detection_README.md` - Upstream vendor detection
- `02_account_extraction_README.md` - Account extraction
- `04_line_items_charge_description` - Charge type extraction (planned)

---

## Appendix: Sample Descriptions by Vendor

### Universal Waste
```
6YD FL Trash
3YD FL Trash
Lock
```

### Active Waste
```
2 YD FRONT LOAD TRASH W/ LOCK BAR
95 GALLON RECYCLE SVC - COMMERCIAL
8 YD FRONT LOAD - OCC
LOCKBAR MONTHLY CHARGE
DISPOSAL CHARGE - PERMANENT TRASH
```

### Boren Brothers
```
8 YD FRONT LOAD TRASH
8 YD FRONT LOAD RECYCLE
30YD ROLL OFF - SCRAP METAL
Compactor Repair - PO OC403336
```

### Rumpke
```
8YD FL/MONTH-MSW
8YD FL/MONTH-CRDBD
20YD RO/LOAD-C&D
RO DISP/TON-STEEL
FUEL SURCHARGE FL
```

### Casella
```
8YD FL WEEKLY TRASH # P/U: 05
96GL CART EOW ZERO SO
40YD STR BOX D&R OCC
DISPOSAL-I/C OCC
```

### Waste Connections
```
8 Yd 3X Wk 1
95 GL 1X WK COM 1
1-3YD REC 2 X WEEKLY
```

### Republic Services
```
1 Waste Container 2 Cu Yd, 1 Lift Per Week
1 Waste Compactor 40 Cu Yd, On Call Service
1 Recycle Cart 95/96 Gal, 1 Lift Per Week
```

---

## Change Log

| Version | Date | Changes |
|---------|------|---------|
| 1.1 | Jan 2026 | Maintenance updates |
| 1.0 | Dec 2024 | Initial release with 15 vendors |

---

## Contact

**Owner:** Shane @ Wasteology  
**Module:** Invoice Processing - Line Item Extraction (Equipment/Material)
