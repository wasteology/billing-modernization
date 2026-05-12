# 04 Line Item Extraction - Charge Description

## Overview

The Line Item Extraction Module (Charge Description) is the fourth stage of Wasteology's invoice processing pipeline. This module parses and categorizes individual charge line items from invoices, extracting the charge type, description, quantity, and amount. This enables detailed billing reconciliation and cost analysis.

---

# Business Documentation

## What It Does

Invoice line items contain various charges like service fees, fuel surcharges, disposal charges, and taxes. This module:

1. **Extracts** individual charge lines from invoice OCR text
2. **Categorizes** each charge into a standard type (Service, Disposal, Fuel, Tax, etc.)
3. **Parses** the quantity and dollar amount for each charge

**Example:**
```
Raw Invoice Line: "8YD FL/MONTH-MSW    $125.00"

Extracted:
  - charge_type: MONTHLY_SERVICE
  - charge_description: "8YD FL/MONTH-MSW"
  - quantity: 1
  - amount: $125.00
```

## Why It Matters

1. **Billing Accuracy:** We need to validate every charge type against contracted rates. A "fuel surcharge" has different validation rules than "monthly service."

2. **Cost Allocation:** Clients need charges broken down by type for budgeting and accounting. They need to know how much they're spending on service vs. fuel vs. disposal.

3. **Rate Auditing:** Different charge types have different pricing structures. Monthly service is flat-rate, disposal is per-ton, fuel fluctuates monthly.

4. **Anomaly Detection:** Unexpected charge types or amounts indicate billing errors or rate changes that need review.

## Charge Type Categories

| Category | Description | % of Charges |
|----------|-------------|--------------|
| **MONTHLY_SERVICE** | Regular container service | 38.9% |
| **FUEL_SURCHARGE** | Fuel/energy surcharges | 16.5% |
| **ADMIN_FEE** | Management & processing fees | 10.4% |
| **FRANCHISE_FEE** | Regulatory & franchise fees | 8.6% |
| **RENTAL** | Equipment rental | 6.2% |
| **HAUL** | Haul/trip/pickup charges | 5.1% |
| **TAX** | Sales & use tax | 5.0% |
| **DISPOSAL** | Tonnage & disposal fees | 3.9% |
| **LOCK** | Lock bar charges | 3.2% |
| **MONITORING** | Sensor & monitoring | 2.5% |
| **ENV_SURCHARGE** | Environmental fees | 0.5% |
| **EXTRA_PICKUP** | Additional service | 0.4% |
| **REBATE** | Credits & rebates | 0.2% |

## Common Charge Descriptions

### Monthly Service
- "Monthly Service Commercial"
- "8YD FL/MONTH-MSW" (Rumpke)
- "COMM FL WASTE PERM 8YD" (GFL)
- "1 Waste Container 2 Cu Yd, 1 Lift Per Week" (Republic)

### Fuel Surcharge
- "Fuel Surcharge Commercial"
- "FUEL SURCHARGE FL" (Rumpke)
- "Fuel/Environmental Charge" (Republic)

### Disposal
- "Disposal Charge"
- "RO DISP/TON-C&D" (Rumpke)
- "Landfill - Trash"

### Haul
- "Empty & Return"
- "Trip Charge"
- "20YD RO/LOAD-C&D" (Rumpke)

### Rental
- "Monthly Rental Industrial"
- "Compactor Rental"
- "20YD RO LEASE" (Rumpke)

## When Updates Are Needed

- **New charge type:** Vendor introduces a charge we haven't seen
- **Misclassification:** Charges landing in wrong category
- **New vendor format:** Different line item structure
- **Amount parsing errors:** Dollar amounts not extracting correctly

---

# Technical Documentation

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│               CHARGE DESCRIPTION EXTRACTION PIPELINE             │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │  Input: vendor_name + raw_ocr_text                       │   │
│  └──────────────────────────────────────────────────────────┘   │
│                              │                                   │
│                              ▼                                   │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │            LINE ITEM EXTRACTION                           │   │
│  │                                                          │   │
│  │  1. Identify line item section in OCR                    │   │
│  │  2. Parse individual charge lines                        │   │
│  │  3. Extract description, quantity, amount                │   │
│  └──────────────────────────────────────────────────────────┘   │
│                              │                                   │
│                              ▼                                   │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │            CHARGE CLASSIFICATION                          │   │
│  │                                                          │   │
│  │  ┌────────────────────────────────────────────────────┐ │   │
│  │  │  CLASSIFICATION RULES                               │ │   │
│  │  │                                                     │ │   │
│  │  │  if matches(DISPOSAL_PATTERNS):                     │ │   │
│  │  │      return DISPOSAL                                │ │   │
│  │  │  elif matches(HAUL_PATTERNS):                       │ │   │
│  │  │      return HAUL                                    │ │   │
│  │  │  elif matches(FUEL_PATTERNS):                       │ │   │
│  │  │      return FUEL_SURCHARGE                          │ │   │
│  │  │  ...                                                │ │   │
│  │  └────────────────────────────────────────────────────┘ │   │
│  └──────────────────────────────────────────────────────────┘   │
│                              │                                   │
│                              ▼                                   │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │  Output: List of charge records                          │   │
│  │                                                          │   │
│  │  [                                                       │   │
│  │    {                                                     │   │
│  │      'charge_type': 'MONTHLY_SERVICE',                   │   │
│  │      'description': '8YD FL/MONTH-MSW',                  │   │
│  │      'quantity': 1,                                      │   │
│  │      'amount': 125.00,                                   │   │
│  │      'unit_of_measure': 'MONTH'                          │   │
│  │    },                                                    │   │
│  │    {                                                     │   │
│  │      'charge_type': 'FUEL_SURCHARGE',                    │   │
│  │      'description': 'FUEL SURCHARGE FL',                 │   │
│  │      'quantity': 1,                                      │   │
│  │      'amount': 18.50,                                    │   │
│  │      'unit_of_measure': 'EACH'                           │   │
│  │    }                                                     │   │
│  │  ]                                                       │   │
│  └──────────────────────────────────────────────────────────┘   │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

## File Structure

```
/mnt/project/
├── charge_description_module.py     # Main module (to be created)
├── billing_chunk_*.csv              # Reference billing records
├── ocr_chunk_*.csv                  # Raw OCR text
├── services_chunk_*.csv             # Rate structure reference
└── line_item_extraction_module.py   # Equipment/material extraction
```

## Output Schema

```python
{
    'charge_type': str,        # Standardized category
    'description': str,        # Original/normalized description
    'quantity': float,         # Number of units
    'amount': float,           # Dollar amount
    'unit_of_measure': str,    # EACH, TON, MONTH, etc.
    'rate': float,             # Per-unit rate (if extractable)
}
```

## Classification Pattern Structure

```python
CHARGE_TYPE_PATTERNS = {
    'MONTHLY_SERVICE': [
        r'Monthly\s+Service',
        r'Container\s+Service',
        r'/MONTH',
        r'(?:Weekly|EOW|Monthly)\s+(?:TRASH|MSW|RECYCL)',
    ],
    'DISPOSAL': [
        r'Disposal\s+Charge',
        r'DISP/TON',
        r'Tonnage',
        r'Landfill',
    ],
    'HAUL': [
        r'Empty\s*&\s*Return',
        r'Trip\s+Charge',
        r'/LOAD',
        r'Haul\s+(?:Charge|Fee)',
    ],
    # ... more categories
}

def classify_charge(description: str) -> str:
    """Classify a charge description into a standard category."""
    for charge_type, patterns in CHARGE_TYPE_PATTERNS.items():
        for pattern in patterns:
            if re.search(pattern, description, re.I):
                return charge_type
    return 'OTHER'
```

## API Reference

### extract_charges(vendor, ocr_text)

Extract all charge line items from invoice OCR.

**Parameters:**
- `vendor` (str): Vendor name for format selection
- `ocr_text` (str): Raw OCR text

**Returns:**
```python
[
    {
        'charge_type': 'MONTHLY_SERVICE',
        'description': '8YD FL/MONTH-MSW',
        'quantity': 1,
        'amount': 125.00,
        'unit_of_measure': 'MONTH'
    },
    # ... more charges
]
```

### classify_charge(description)

Classify a single charge description.

**Parameters:**
- `description` (str): Charge line description

**Returns:**
- `str`: Charge type category

### parse_amount(text)

Extract dollar amount from text.

**Parameters:**
- `text` (str): Text containing amount

**Returns:**
- `float` or `None`: Extracted amount

## OCR Parsing Strategies

### Columnar Tables

Invoice tables often OCR as separate columns:

```
# Original table:
DESCRIPTION          QTY    AMOUNT
8YD FL WEEKLY        4      $500.00
FUEL SURCHARGE       1      $45.00

# OCR output:
DESCRIPTION
8YD FL WEEKLY
FUEL SURCHARGE
QTY
4
1
AMOUNT
$500.00
$45.00
```

**Parsing strategy:**
```python
def parse_columnar(lines):
    # Find column headers
    desc_idx = find_header_index(lines, 'DESCRIPTION')
    qty_idx = find_header_index(lines, 'QTY')
    amt_idx = find_header_index(lines, 'AMOUNT')
    
    # Extract values by relative position
    descriptions = extract_column_values(lines, desc_idx)
    quantities = extract_column_values(lines, qty_idx)
    amounts = extract_column_values(lines, amt_idx)
    
    # Align by count
    return align_columns(descriptions, quantities, amounts)
```

### Inline Format

Some invoices use inline formatting:

```
"8YD FL WEEKLY @ $125.00 x 4 = $500.00"
```

**Pattern:**
```python
inline_pattern = re.compile(
    r'(.+?)\s*@\s*\$?([\d,]+\.?\d*)\s*x\s*(\d+)\s*=\s*\$?([\d,]+\.?\d*)'
)
```

### Vendor-Specific Parsers

Each high-volume vendor may need custom parsing:

```python
def parse_rumpke_charges(lines):
    """Rumpke format: CODE DESCRIPTION $AMOUNT"""
    charges = []
    for line in lines:
        match = re.match(r'(.+?)\s+\$([\d,]+\.?\d*)\s*$', line)
        if match:
            charges.append({
                'description': match.group(1).strip(),
                'amount': float(match.group(2).replace(',', ''))
            })
    return charges
```

## Amount Parsing

```python
def parse_amount(text: str) -> Optional[float]:
    """Extract dollar amount from text."""
    # Standard format: $1,234.56
    match = re.search(r'\$\s*([\d,]+\.?\d*)', text)
    if match:
        return float(match.group(1).replace(',', ''))
    
    # Negative: -$45.00 or ($45.00)
    match = re.search(r'[-\(]\s*\$?\s*([\d,]+\.?\d*)\)?', text)
    if match:
        return -float(match.group(1).replace(',', ''))
    
    return None
```

## Quantity Parsing

```python
def parse_quantity(text: str) -> Optional[float]:
    """Extract quantity from text."""
    patterns = [
        (r'(?:QTY|Qty)[:\s]*(\d+)', 1),           # QTY: 4
        (r'x\s*(\d+)', 1),                         # x4
        (r'#\s*P/U[:\s]*(\d+)', 1),                # # P/U: 05
        (r'([\d.]+)\s*(?:TON|TONS)', 1),           # 2.5 TONS
        (r'(\d+)\s*X\s*(?:WEEK|WK)', lambda m: int(m.group(1)) * 4),  # 2X WEEKLY → 8/month
    ]
    
    for pattern, multiplier in patterns:
        match = re.search(pattern, text, re.I)
        if match:
            val = float(match.group(1))
            if callable(multiplier):
                return multiplier(match)
            return val * multiplier
    
    return 1  # Default to 1
```

## Testing

### Unit Tests

```python
def test_classify_charge():
    test_cases = [
        ("Monthly Service Commercial", "MONTHLY_SERVICE"),
        ("8YD FL/MONTH-MSW", "MONTHLY_SERVICE"),
        ("Fuel Surcharge Commercial", "FUEL_SURCHARGE"),
        ("FUEL SURCHARGE FL", "FUEL_SURCHARGE"),
        ("Disposal Charge", "DISPOSAL"),
        ("RO DISP/TON-C&D", "DISPOSAL"),
        ("Empty & Return", "HAUL"),
        ("Trip Charge", "HAUL"),
        ("Monthly Rental Industrial", "RENTAL"),
        ("Tax Commercial", "TAX"),
    ]
    
    for desc, expected in test_cases:
        result = classify_charge(desc)
        assert result == expected, f"Failed: {desc} → {result}"
```

### Integration Tests

```python
def test_extract_charges():
    ocr_text = """
    8YD FL/MONTH-MSW    $125.00
    FUEL SURCHARGE FL   $18.50
    """
    
    charges = extract_charges('Rumpke', ocr_text)
    
    assert len(charges) == 2
    assert charges[0]['charge_type'] == 'MONTHLY_SERVICE'
    assert charges[0]['amount'] == 125.00
    assert charges[1]['charge_type'] == 'FUEL_SURCHARGE'
    assert charges[1]['amount'] == 18.50
```

## Troubleshooting

| Symptom | Likely Cause | Solution |
|---------|--------------|----------|
| Charge not classified | Pattern missing | Add new pattern for charge type |
| Wrong category | Pattern order | Move specific patterns before generic |
| Amount None | OCR format variation | Add amount pattern variant |
| Quantity wrong | Frequency not parsed | Handle vendor-specific frequency format |
| Missing charges | Table parsing failed | Check columnar alignment logic |
| Duplicate charges | Line parsed twice | Add deduplication check |

## Performance Considerations

- Pre-compile all regex patterns
- Use early returns in classification (most common types first)
- Cache vendor-specific parser selection
- Batch process multiple invoices efficiently

## Maintenance

### Adding a New Charge Type

1. Analyze billing data to find patterns
2. Create pattern list for new category
3. Add to `CHARGE_TYPE_PATTERNS`
4. Add test cases
5. Run full test suite

### Adding a New Vendor

1. Collect 20+ sample invoices
2. Analyze OCR format (columnar vs inline)
3. Create vendor-specific parser if needed
4. Add to vendor dispatcher
5. Validate against known charges

---

## Related Documentation

- `04_line_item_charge_description_INSTRUCTIONS.md` - Claude instructions
- `03_line_item_equipment_material_README.md` - Equipment extraction
- `02_account_extraction_README.md` - Account extraction
- `01_vendor_detection_README.md` - Vendor detection

---

## Appendix: Charge Type Distribution

Based on analysis of 50,000 billing records:

```
MONTHLY_SERVICE      19,459  (38.9%)
FUEL_SURCHARGE        8,236  (16.5%)
ADMIN_FEE             5,210  (10.4%)
FRANCHISE_FEE         4,293   (8.6%)
RENTAL                3,082   (6.2%)
HAUL                  2,529   (5.1%)
TAX                   2,504   (5.0%)
DISPOSAL              1,963   (3.9%)
LOCK                  1,597   (3.2%)
MONITORING            1,231   (2.5%)
ENV_SURCHARGE           263   (0.5%)
EXTRA_PICKUP            188   (0.4%)
REBATE                  118   (0.2%)
```

---

## Appendix: Vendor Format Quick Reference

| Vendor | Service Format | Surcharge Format | Disposal Format |
|--------|----------------|------------------|-----------------|
| Rumpke | `8YD FL/MONTH-MSW` | `FUEL SURCHARGE FL` | `RO DISP/TON-C&D` |
| Casella | `8YD FL WEEKLY TRASH` | `FUEL/ENVIRO` | `DISPOSAL-I/C OCC` |
| Republic | `Waste Container 2 Cu Yd` | `Fuel/Environmental` | `Disposal Fee` |
| WM | `Pickup 1 Yards Trash DMP` | `Fuel/Environmental` | `Disposal` |
| GFL | `COMM FL WASTE PERM 8YD` | `FUEL SURCHARGE` | `DISPOSAL` |
| WC | `1-8YD CONT 2 X WEEKLY` | `FUEL SURCHARGE` | `DISPOSAL` |

---

## Change Log

| Version | Date | Changes |
|---------|------|---------|
| 1.0 | Jan 2026 | Initial implementation with 13 charge categories |

---

## Contact

**Owner:** Shane @ Wasteology  
**Module:** Invoice Processing - Line Item Extraction (Charge Description)
