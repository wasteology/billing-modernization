# Line Item Extraction (Charge Description) - Claude Instructions

## Purpose

This document provides all context needed for Claude to efficiently update charge description extraction and categorization patterns. Load this document whenever you need to add new charge types, fix categorization issues, or improve parsing accuracy.

---

## Module Overview

**File:** `/mnt/project/charge_description_module.py` (to be created)  
**Function:** Extract and categorize charge descriptions from invoice line items  
**Input:** Raw OCR text + vendor name  
**Output:** Structured charge records with type, description, quantity, amount

---

## Data Files Reference

| File | Purpose | Key Columns |
|------|---------|-------------|
| `billing_chunk_*.csv` (1-6) | Reference billing records | `charge_description`, `price`, `cost` |
| `ocr_chunk_*.csv` (1-7) | Raw OCR for parsing | `raw_text` |
| `services_chunk_*.csv` (1-2) | Rate structure reference | `charge_type_*`, `cost_*` |

---

## Output Schema

### charge_type
Standardized charge category:

| Category | Description | Volume |
|----------|-------------|--------|
| `MONTHLY_SERVICE` | Regular container service | 19,459 |
| `FUEL_SURCHARGE` | Fuel/energy surcharge | 8,236 |
| `ADMIN_FEE` | Management/processing fees | 5,210 |
| `FRANCHISE_FEE` | Franchise/regulatory fees | 4,293 |
| `RENTAL` | Equipment rental charges | 3,082 |
| `HAUL` | Haul/trip/pickup charges | 2,529 |
| `TAX` | Sales/use tax | 2,504 |
| `DISPOSAL` | Disposal/tonnage fees | 1,963 |
| `LOCK` | Lock bar charges | 1,597 |
| `MONITORING` | Sensor/monitoring fees | 1,231 |
| `ENV_SURCHARGE` | Environmental fees | 263 |
| `EXTRA_PICKUP` | Additional service charges | 188 |
| `REBATE` | Credits/rebates (negative) | 118 |

### charge_description
Normalized description string (e.g., "Monthly Service Commercial")

### quantity
Number of units (pickups, tons, days, etc.)

### amount
Dollar amount for the charge

### unit_of_measure
Unit type: `EACH`, `TON`, `YARD`, `MONTH`, `TRIP`, etc.

---

## Charge Type Classification Rules

### MONTHLY_SERVICE
Regular recurring container service charges.

**Keywords:** `Monthly Service`, `Service Charge`, `Regular Service`, `Container Service`, `Perm`, `Permanent`

**Patterns:**
```python
MONTHLY_SERVICE_PATTERNS = [
    r'Monthly\s+Service',
    r'Container\s+Service',
    r'\d+\s*YD.*(?:Weekly|Monthly|EOW)',
    r'PERM(?:ANENT)?\s+SERVICE',
    r'FL/(?:MONTH|WEEK)',  # Rumpke format
]
```

**Examples:**
- "Monthly Service Commercial" → MONTHLY_SERVICE
- "8YD FL/MONTH-MSW" → MONTHLY_SERVICE
- "COMM FL WASTE PERM 8YD" → MONTHLY_SERVICE

---

### DISPOSAL
Tonnage, tipping, and landfill charges.

**Keywords:** `Disposal`, `Tonnage`, `Tipping`, `Landfill`, `Per Ton`, `Dump`

**Patterns:**
```python
DISPOSAL_PATTERNS = [
    r'Disposal\s+Charge',
    r'(?:Per|/)\s*Ton',
    r'Tonnage',
    r'Tipping\s+Fee',
    r'Landfill',
    r'DISP/TON',  # Rumpke format
    r'Dump\s+(?:Fee|Charge)',
]
```

**Examples:**
- "Disposal Charge" → DISPOSAL
- "RO DISP/TON-C&D" → DISPOSAL
- "Landfill - Trash" → DISPOSAL
- "Over Tonnage Limit Fee" → DISPOSAL

---

### HAUL
Trip, pickup, and delivery charges.

**Keywords:** `Haul`, `Trip`, `Empty & Return`, `Pick Up`, `Pull`, `Delivery`, `Switch`

**Patterns:**
```python
HAUL_PATTERNS = [
    r'Haul\s+(?:Charge|Fee)',
    r'Empty\s*&\s*Return',
    r'Trip\s+Charge',
    r'(?:Extra|Final|Hand)\s+Pick\s*Up',
    r'Switch\s*Out',
    r'Delivery',
    r'Roll\s*Off\s+Haul',
    r'/LOAD',  # Rumpke RO/LOAD format
]
```

**Examples:**
- "Empty & Return" → HAUL
- "Trip Charge" → HAUL
- "20YD RO/LOAD-C&D" → HAUL
- "Switch Out 20 YD Roll Off" → HAUL

---

### RENTAL
Container and equipment rental charges.

**Keywords:** `Rental`, `Lease`, `Container Rent`, `Equipment Rent`

**Patterns:**
```python
RENTAL_PATTERNS = [
    r'(?:Monthly|Daily|Weekly)\s+Rental',
    r'Container\s+Rental',
    r'Equipment\s+Rental',
    r'Lease',
    r'Receiver\s+Container\s+Rental',
    r'Compactor\s+Rental',
    r'RO\s+LEASE',  # Rumpke format
]
```

**Examples:**
- "Monthly Rental Industrial" → RENTAL
- "Compactor Rental" → RENTAL
- "20YD RO LEASE" → RENTAL

---

### FUEL_SURCHARGE
Fuel and energy-related surcharges.

**Keywords:** `Fuel`, `Energy`, `FSC`

**Patterns:**
```python
FUEL_PATTERNS = [
    r'Fuel\s+Surcharge',
    r'Energy\s+(?:Surcharge|Fee)',
    r'\bFSC\b',
    r'FUEL\s+SURCHARGE\s+(?:FL|RO)',  # Rumpke
]
```

**Examples:**
- "Fuel Surcharge Commercial" → FUEL_SURCHARGE
- "FUEL SURCHARGE FL" → FUEL_SURCHARGE

---

### ENV_SURCHARGE
Environmental and sustainability fees.

**Keywords:** `Environmental`, `Sustainability`, `Green`, `Eco`

**Patterns:**
```python
ENV_PATTERNS = [
    r'Environmental\s+(?:Surcharge|Fee)',
    r'Sustainability\s+Fee',
    r'Green\s+Fee',
]
```

---

### FRANCHISE_FEE
Franchise, regulatory, and municipal fees.

**Keywords:** `Franchise`, `Regulatory`, `Municipal`, `City Fee`

**Patterns:**
```python
FRANCHISE_PATTERNS = [
    r'Franchise\s+Fee',
    r'Regulatory\s+(?:Fee|Charge)',
    r'Municipal\s+Fee',
    r'City\s+(?:Fee|Surcharge)',
    r'Local\s+Surcharges?/Fees',
]
```

---

### TAX
Sales and use taxes.

**Keywords:** `Tax`, `Sales Tax`, `Use Tax`

**Patterns:**
```python
TAX_PATTERNS = [
    r'(?:Sales|Use)?\s*Tax',
    r'Tax\s+(?:Commercial|Industrial)',
]
```

**Note:** Tax lines often appear at the end of invoices and may need special handling.

---

### ADMIN_FEE
Administrative and management fees.

**Keywords:** `Admin`, `Management`, `Processing`, `Service Fee`

**Patterns:**
```python
ADMIN_PATTERNS = [
    r'(?:Admin|Administrative)\s+Fee',
    r'Management\s+Fee',
    r'Processing\s+Fee',
    r'Service\s+(?:Fee|Charge)',
    r'WG\s+Admin\s+Fee',
]
```

---

### EXTRA_PICKUP
Additional service and overage charges.

**Keywords:** `Extra`, `Additional`, `Overage`, `On Call`

**Patterns:**
```python
EXTRA_PATTERNS = [
    r'Extra\s+(?:Pick\s*Up|Service|Pickup)',
    r'Additional',
    r'Overage',
    r'On\s+Call',
    r'FL/EXTRA',  # Rumpke format
]
```

---

### LOCK
Lock bar and security charges.

**Keywords:** `Lock`, `Lockbar`, `Security`

**Patterns:**
```python
LOCK_PATTERNS = [
    r'Lock\s*Bar',
    r'Lock\s+(?:Charge|Fee)',
    r'Security\s+(?:Lock|Device)',
]
```

---

### MONITORING
Sensor and monitoring charges.

**Keywords:** `Monitor`, `Sensor`, `Compactor Monitor`

**Patterns:**
```python
MONITORING_PATTERNS = [
    r'(?:Compactor)?\s*Monitoring',
    r'(?:Front\s+Load)?\s*Sensor',
    r'SmartTrash',
    r'Fill\s+Level\s+Monitor',
]
```

---

### REBATE
Credits, rebates, and negative charges.

**Keywords:** `Rebate`, `Credit`, `Refund`

**Patterns:**
```python
REBATE_PATTERNS = [
    r'(?:Recycling)?\s*Rebate',
    r'Credit',
    r'Refund',
    r'Adjustment\s*\(?(?:CR|Credit)',
]
```

**Note:** Rebates should have negative amounts.

---

## OCR Parsing Strategies

### Strategy 1: Columnar Table Parsing

Many invoices have tables with columns like:
```
DESCRIPTION          QTY    RATE    AMOUNT
8YD FL WEEKLY        4      $125    $500.00
FUEL SURCHARGE       1      $45     $45.00
```

OCR often captures columns separately:
```
DESCRIPTION
8YD FL WEEKLY
FUEL SURCHARGE
QTY
4
1
RATE
$125
$45
AMOUNT
$500.00
$45.00
```

**Parsing approach:**
1. Identify column headers
2. Track column positions
3. Align values by position/count

### Strategy 2: Inline Parsing

Some vendors use inline formats:
```
"8YD FL WEEKLY TRASH @ $125.00 x 4 = $500.00"
```

**Pattern:**
```python
inline_pattern = re.compile(
    r'(.+?)\s*@\s*\$?([\d,]+\.?\d*)\s*x\s*(\d+)\s*=\s*\$?([\d,]+\.?\d*)',
    re.I
)
```

### Strategy 3: Line-by-Line with Context

Parse lines sequentially, maintaining state:
```python
def parse_charges(lines, vendor):
    current_charge = {}
    charges = []
    
    for line in lines:
        if is_description(line):
            if current_charge:
                charges.append(current_charge)
            current_charge = {'description': line}
        elif is_amount(line):
            current_charge['amount'] = extract_amount(line)
        elif is_quantity(line):
            current_charge['quantity'] = extract_quantity(line)
    
    return charges
```

---

## Vendor-Specific Formats

### Rumpke
```
8YD FL/MONTH-MSW              $125.00
8YD FL/EXTRA-MSW              $45.00
RO DISP/TON-C&D               $65.00/TON
FUEL SURCHARGE FL             $18.50
```

**Categorization:**
- `/MONTH` → MONTHLY_SERVICE
- `/EXTRA` → EXTRA_PICKUP
- `DISP/TON` → DISPOSAL
- `/LOAD` → HAUL
- `FUEL SURCHARGE` → FUEL_SURCHARGE

### Casella
```
8YD FL WEEKLY TRASH # P/U: 05    $625.00
6YD FL EXTRA P/U - TRASH         $55.00
DISPOSAL-I/C OCC                 $85.00
```

**Categorization:**
- `WEEKLY`, `EOW` (frequency) → MONTHLY_SERVICE
- `EXTRA P/U` → EXTRA_PICKUP
- `DISPOSAL` → DISPOSAL

### Republic Services
```
1 Waste Container 2 Cu Yd, 1 Lift Per Week    $95.00
Fuel/Environmental Charge                      $12.50
```

**Categorization:**
- `Container...Lift Per Week` → MONTHLY_SERVICE
- `Fuel/Environmental` → FUEL_SURCHARGE (or split)

### Waste Connections
```
1-8YD CONT 2 X WEEKLY           $245.00
FUEL SURCHARGE                  $28.00
LOCAL SURCHARGES/FEES           $15.00
```

### Waste Management
```
Pickup 1 Yards Trash DMP Weekly x1    $89.00
Fuel/Environmental Charge              $8.50
Regulatory Cost Recovery Fee           $6.00
```

---

## Amount Extraction Patterns

```python
AMOUNT_PATTERNS = [
    # Standard: $1,234.56
    r'\$\s*([\d,]+\.?\d*)',
    
    # Negative: -$45.00 or ($45.00) or $45.00 CR
    r'-\s*\$\s*([\d,]+\.?\d*)',
    r'\(\$\s*([\d,]+\.?\d*)\)',
    r'\$\s*([\d,]+\.?\d*)\s*CR',
    
    # Rate format: $65.00/TON
    r'\$\s*([\d,]+\.?\d*)\s*/\s*(?:TON|YARD|EACH)',
]
```

---

## Quantity Extraction Patterns

```python
QUANTITY_PATTERNS = [
    # Explicit: QTY: 4, Qty 4, x4
    r'(?:QTY|Qty)[:\s]*(\d+)',
    r'x\s*(\d+)',
    
    # Pickup count: # P/U: 05
    r'#\s*P/U[:\s]*(\d+)',
    
    # Frequency implied: 2 X WEEKLY (multiply by 4 for monthly)
    r'(\d+)\s*X\s*(?:WEEK|WK)',
    
    # Tonnage: 2.5 TONS
    r'([\d.]+)\s*(?:TON|TONS)',
]
```

---

## Workflow: Adding a New Charge Type

### Step 1: Identify the Pattern

Analyze billing data for the new charge type:
```python
billing = pd.read_csv('billing_chunk_1.csv')
samples = billing[billing['charge_description'].str.contains('NEW PATTERN', case=False)]
print(samples['charge_description'].value_counts())
```

### Step 2: Create Classification Pattern

```python
NEW_TYPE_PATTERNS = [
    r'pattern_1',
    r'pattern_2',
]
```

### Step 3: Add to Classifier

```python
def classify_charge(description):
    for pattern in NEW_TYPE_PATTERNS:
        if re.search(pattern, description, re.I):
            return 'NEW_TYPE'
    # ... existing classifications
```

### Step 4: Test

```python
test_cases = [
    ("New Charge Description 1", "NEW_TYPE"),
    ("New Charge Description 2", "NEW_TYPE"),
]

for desc, expected in test_cases:
    result = classify_charge(desc)
    assert result == expected
```

---

## Common Issues and Fixes

### Issue 1: Misclassification

**Symptom:** Charge categorized incorrectly

**Fix:** Adjust pattern order (more specific before generic):
```python
# WRONG: Generic first
if 'service' in desc.lower():
    return 'MONTHLY_SERVICE'
if 'extra' in desc.lower():
    return 'EXTRA_PICKUP'

# RIGHT: Specific first
if 'extra' in desc.lower() and 'service' in desc.lower():
    return 'EXTRA_PICKUP'
if 'service' in desc.lower():
    return 'MONTHLY_SERVICE'
```

### Issue 2: Amount Parsing Failure

**Symptom:** Amount returns None

**Fix:** Handle OCR variations:
```python
# Handle missing decimal, OCR errors
amount_str = amount_str.replace('S', '$').replace('O', '0')
if '.' not in amount_str:
    amount_str = amount_str[:-2] + '.' + amount_str[-2:]
```

### Issue 3: Multi-Line Charges

**Symptom:** Description and amount on different lines

**Fix:** Use state machine parsing:
```python
pending_description = None
for line in lines:
    if is_description(line):
        pending_description = line
    elif is_amount(line) and pending_description:
        charges.append({
            'description': pending_description,
            'amount': parse_amount(line)
        })
        pending_description = None
```

---

## Testing Commands

```python
# Test classification
from charge_description_module import classify_charge

test_cases = [
    ("Monthly Service Commercial", "MONTHLY_SERVICE"),
    ("Fuel Surcharge", "FUEL_SURCHARGE"),
    ("Disposal Charge", "DISPOSAL"),
    ("Empty & Return", "HAUL"),
]

for desc, expected in test_cases:
    result = classify_charge(desc)
    print(f"{desc} → {result} (expected: {expected})")
```

---

## Related Modules

| Module | Relationship |
|--------|--------------|
| `01_vendor_detection` | Provides vendor for format selection |
| `02_account_extraction` | Links charges to account |
| `03_line_items_equipment_material` | Provides equipment context |

---

## Version History

| Version | Changes |
|---------|---------|
| Planned | Initial implementation with 13 charge categories |

---

## Contact & Ownership

**Owner:** Shane @ Wasteology
**Module:** Invoice Processing System - Line Item Extraction (Charge Description)
**Last Updated:** January 2026
