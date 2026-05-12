# Plan: Build Remaining Date Extraction Patterns

## Pre-Requisite: Fix Permission Settings ✅ DONE

Settings files fixed in both locations:
- `/home/scstclair/projects/parsing_engines/.claude/settings.local.json`
- `/home/scstclair/projects/parsing_engines/dates/.claude/settings.local.json`

---

## Summary

Build regex patterns for the ~760 vendors missing from the date extraction module, bringing coverage from 35.5% to 100%.

## Current State

| Metric | Value |
|--------|-------|
| Vendors in vendor_detection | 1,179 |
| Vendors with date patterns | 734 |
| Missing patterns | 445 |
| Current tranche | 62 (completed) |

## Approach

Work in tranches of 10-12 vendors, prioritized by invoice volume (most common vendors first).

### For Each Vendor:

1. **Get sample OCR** from `training_data/ocr_chunks/raw_ocr_text.csv`
2. **Identify pattern type**:
   - Date label (Invoice Date, Statement Date, DATE, etc.)
   - Position (inline, columnar, wide columnar, reverse)
   - Format (MM/DD/YYYY, Month DD YYYY, etc.)
3. **Write extractor function** following existing conventions
4. **Add dictionary entry** to `VENDOR_DATE_ADDITIONS`
5. **Test against sample**

### Pattern Templates (from CLAUDE.md):

- **Inline**: Label and value on same line
- **Columnar**: Label on one line, value 1-5 lines below
- **Wide Columnar**: Label and value 5-10 lines apart
- **Reverse**: Value BEFORE label
- **Month name**: January 15, 2025 style

## Files to Modify

- `dates/date_extraction_additions.py` - Add extractor functions + dict entries

## Execution Order

1. Query OCR CSV to get vendor invoice counts (prioritize high-volume)
2. Process vendors in batches of 10-12 (tranches)
3. For each tranche:
   - Get samples for each vendor
   - Analyze date label/format/position
   - Write extractor function
   - Add dict entry
   - Test the pattern
4. Commit after each 3-4 tranches (~40-50 vendors)

## Verification

After each tranche:
```python
# Test all new patterns against OCR samples
for vendor in new_vendors:
    extractor = VENDOR_DATE_ADDITIONS[vendor]['extract']
    sample = get_sample_for_vendor(vendor)
    result = extractor(sample)
    print(f"{vendor}: {result}")
```

## Estimated Scope

- 591 vendors / 12 per tranche = ~49 tranches remaining
- Currently at Tranche 51

## Next Steps

1. Query OCR data for top unconfigured vendors by volume
2. Continue Tranche 45
3. Commit after every 3-4 tranches
