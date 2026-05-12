# Amount Due Extraction Module

Extracts bill total/amount due from raw OCR invoice text.

## Coverage

~90.9% on production invoice corpus (Feb 2026)

## Usage

```python
from parsing_engines.amount_due import extract_bill_total

# Extract amount from OCR text
amount = extract_bill_total(raw_ocr_text)
if amount:
    print(f"Bill total: ${amount:.2f}")
```

## Patterns

The module uses 40+ patterns organized by priority:

### 1. Multiline Patterns (Highest Priority)
Many vendors (Waste Connections, Republic, WM, GFL) put amounts on the **next line** after labels in OCR:
```
Total Due
$ 92.93
```

### 2. Same-Line Patterns
Standard patterns like:
- `Total Due: $123.45`
- `Amount Due: $123.45`
- `Please Pay: $123.45`

### 3. Vendor-Specific Patterns
- Waste Management: `Total Current Billing`
- Republic Services: `Account Balance`
- GFL: `Total Due:`

### 4. OCR Artifact Tolerant
Handles collapsed spaces common in poor OCR:
- `AMOUNTDUE` (instead of `AMOUNT DUE`)
- `TOTALDUE` (instead of `TOTAL DUE`)

## OCR Text Handling

OCR CSV exports have literal `\n` strings, not actual newlines:

```python
# Raw OCR text looks like:
"Total Due\\n$ 92.93"

# The module automatically converts these to real newlines
# for multiline pattern matching to work
```

## CLI Testing

```bash
# Test extraction on sample text
python -m parsing_engines.amount_due.amount_due_extraction_engine "Total Due: \$123.45"

# Show pattern count
python -m parsing_engines.amount_due.amount_due_extraction_engine
```

## Adding New Patterns

Add patterns to `TOTAL_PATTERNS` in `amount_due_extraction_engine.py`:

```python
# Format: (regex_pattern, is_multiline_hint)
TOTAL_PATTERNS = [
    # Multiline pattern (amount on next line)
    (r'(?:NEW\s*LABEL)\s*\n\s*\$?\s*([\d,]+\.\d{2})', True),

    # Same-line pattern
    (r'(?:NEW\s*LABEL)[:\s]*\$?\s*([\d,]+\.?\d*)', False),
]
```

## Files

| File | Description |
|------|-------------|
| `amount_due_extraction_engine.py` | Main extraction logic and patterns |
| `__init__.py` | Module exports |
| `README.md` | This file |

---

*Module created: February 2026*
