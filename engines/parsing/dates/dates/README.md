# Invoice Date Extraction Module

Extracts invoice/statement dates from raw OCR invoice text.

## Coverage

~53.6% on production invoice corpus (Feb 2026)

## Usage

```python
from parsing_engines.dates import extract_invoice_date, extract_invoice_month

# Extract full date (YYYY-MM-DD)
date = extract_invoice_date(raw_ocr_text)
if date:
    print(f"Invoice date: {date}")  # 2025-01-15

# Extract month only (YYYY-MM)
month = extract_invoice_month(raw_ocr_text)
if month:
    print(f"Invoice month: {month}")  # 2025-01
```

## Patterns

The module uses 16+ patterns organized by format:

### 1. Labeled Date Patterns (Highest Priority)
```
Invoice Date: 01/15/2025
Statement Date: 01-15-2025
Bill Date: 01/15/25
```

### 2. Generic Date Patterns
```
Date: 01/15/2025
Date: 01-15-25
```

### 3. Month Name Patterns
```
Invoice Date: January 15, 2025
Date: Jan 15, 2025
```

### 4. Service Period (First Date)
```
Service Period: 01/15/2025 - 02/15/2025
```

### 5. ISO Format
```
Date: 2025-01-15
```

### 6. OCR Artifact Tolerant
Handles collapsed spaces:
```
InvoiceDate: 01/15/2025
StatementDate: 01/15/2025
```

## Date Validation

Dates are validated to ensure:
- Month is 1-12
- Day is 1-31
- Year is 2020-2030 (reasonable invoice range)

## CLI Testing

```bash
# Test extraction on sample text
python -m parsing_engines.dates.date_extraction_engine "Invoice Date: 01/15/2025"

# Show pattern count
python -m parsing_engines.dates.date_extraction_engine
```

## Adding New Patterns

Add patterns to `DATE_PATTERNS` in `date_extraction_engine.py`:

```python
# Format: (regex_pattern, date_format)
# date_format: 'MDY' for MM/DD/YYYY, 'YMD' for YYYY-MM-DD, 'MONTH' for spelled out
DATE_PATTERNS = [
    # New pattern for DD/MM/YYYY format (European)
    (r'(?:Invoice\s*Date)[:\s]+(\d{1,2})[/\-](\d{1,2})[/\-](\d{4})', 'DMY'),  # Note: Need to add DMY handler
]
```

## Files

| File | Description |
|------|-------------|
| `date_extraction_engine.py` | Main extraction logic and patterns |
| `__init__.py` | Module exports |
| `README.md` | This file |

---

*Module created: February 2026*
