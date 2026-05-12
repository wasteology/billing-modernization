# Output Spec — Column Reference

Every vendor extract CSV produced by `executor.py` conforms to this column contract.
Columns appear in the order listed below. Vendor-specific fields (e.g., `wo_number`,
`site_id`) are appended after column 22 (`flag`).

Each row in the output represents **one charge line** on an invoice. Header fields
(`invoice_number`, `bill_total`, etc.) repeat on every charge row.

---

## Column Definitions

### 1. `pdf_filename`
**Level**: Invoice
**Required**: Yes
**Source**: OCR pipeline metadata

The base filename of the source PDF (e.g., `CASD01 - October 25 - EDCO.pdf`).
Passed through from `ocr_results.csv` — never extracted from OCR text.
Used as the primary identifier to trace a row back to its source document.

---

### 2. `pdf_link`
**Level**: Invoice
**Required**: Yes
**Source**: Computed from `pdf_path` in OCR metadata

A `file://` URL to the source PDF, built by `_build_pdf_link()`:
- Normalizes `/Invoices/` → `/invoices/` (case fix)
- URL-encodes spaces and special characters (safe chars: `/:@`)

```
/path/to/CASD01 - October 25 - EDCO.pdf
  → file:///path/to/CASD01%20-%20October%2025%20-%20EDCO.pdf
```

Enables one-click navigation from the review CSV to the source PDF.

---

### 3. `invoice_number`
**Level**: Header
**Required**: Yes (all patterns except `edco_disposal`)
**Source**: `extraction_stages` → regex named group → context field

Extracted from the OCR header block via a `search`-method stage with a vendor-specific
regex. Captured as a named group (e.g., `(?P<invoice_number>\d+)`). Carried as-is —
no normalization applied. Missing → `HDR_MISSING: invoice_number` flag.

**Exception** — `rob_invoice`: Robinson invoices have two totals (past-due balance vs.
current period). `invoice_number` is extracted from the current-period header only.

---

### 4. `invoice_date`
**Level**: Header
**Required**: No
**Source**: `extraction_stages` → `date_parse` transform

Extracted from the header block. After capture, the `date_parse` transform tries a
list of vendor-specific format strings (e.g., `%m/%d/%Y`, `%B %d, %Y`, `%m-%d-%Y`)
and normalizes to `MM/DD/YYYY`. If no format matches, the field is left as the raw
captured string.

---

### 5. `account_number`
**Level**: Header
**Required**: Yes
**Source**: `extraction_stages` regex

The customer account number as it appears on the invoice. All vendor-specific field
name variants (`account_name`, `vendor_account`, `customer_id`) are mapped to
`account_number` in `output_spec` — never passed through under an alternate name.

Some vendors don't include account numbers. For confirmed `NO_ACCOUNT` vendors the
field is blank; no `HDR_MISSING` flag is raised (pattern opts out of the requirement).

---

### 6. `bill_total`
**Level**: Header
**Required**: Yes
**Source**: `extraction_stages` → `currency_parse` transform

The total amount due as printed on the invoice. Extracted via regex from the header
block, then cleaned by `currency_parse` (strips `$`, commas → `float`).

This value is the **validation target**: `charge_sum` must equal `bill_total` within
`$0.02` for the invoice to be marked `valid = True`.

**Exception** — `rob_invoice`: Uses `invoice_total` (current period only) as the
validation target, not `bill_total` (which includes past-due balance).

---

### 7. `charge_sum`
**Level**: Computed
**Required**: Yes
**Source**: `validate()` → repeated on every charge row

```python
charge_sum = round(sum(c.get('charge_total', 0) or 0 for c in charges), 2)
```

Sum of all `charge_total` values extracted from this invoice. Rounded to 2 decimal
places. The same value is written to every charge row for that invoice.

---

### 8. `num_charges`
**Level**: Computed
**Required**: Yes
**Source**: `len(charges)` → repeated on every charge row

Count of charge lines extracted from this invoice. Written identically to every row.
Use this to quickly spot invoices where the charge pipeline extracted too few or too
many lines relative to expectation.

---

### 9. `valid`
**Level**: Computed
**Required**: Yes
**Source**: `validate()` → `output_spec.charge_sum_check`

| Value | Condition |
|-------|-----------|
| `True` | `abs(bill_total - charge_sum) < 0.02` |
| `False` | `abs(diff) >= 0.02` |
| `None` | `bill_total` is garbled or missing, or `charge_sum_check: false` in pattern |

`trashbilling_standard` is the only pattern with `charge_sum_check: false` — it
always produces `valid = None`.

---

### 10. `diff`
**Level**: Computed
**Required**: Yes
**Source**: `validate()` stored as `_diff`

```python
diff = round(bill_total - charge_sum, 2)
```

Positive `diff` → charges are **under-captured** (lines missed). The tracker records
this as `status = UNDER_CAPTURE`.
Negative `diff` → charges are **over-captured** (duplicate or phantom lines). Tracker
records as `status = DIFF`.
`$0.00` → exact match (usual outcome when `valid = True`).
`None` → `bill_total` could not be parsed.

Small non-zero diffs ($1–$6) typically trace to OCR noise (garbled amounts at page
transitions). Large diffs indicate structural extraction failures — missed blocks or
unmatched charge sections.

---

### 11. `service_date`
**Level**: Charge
**Required**: Yes
**Source**: `charge_pipeline` → `charge_detect.date_pattern`

The service date associated with a charge line. Extracted by matching
`charge_detect.date_pattern` at the start of each line (or via `date_split_raw` chunk
mode). Format controlled by `charge_detect.date_format` template (e.g.,
`"{0}/{1}/{2}"` → `MM/DD/YYYY`).

Lines that fail the date match are skipped if `charge_detect.require_date: true`.
For patterns where charge lines lack individual dates (some block-mode vendors), the
field may be empty or inherited from the block header.

---

### 12. `description`
**Level**: Charge
**Required**: Yes
**Source**: `charge_pipeline` → `desc_extract_mode`

The raw charge description text after amounts and dates are stripped. Extraction mode
is controlled by `charge_extract.desc_extract_mode`:

| Mode | Logic |
|------|-------|
| `after_date` *(default)* | Text after the matched date, amounts stripped |
| `before_wo` | Text between date end and first WO#/amount cluster (Cockey's) |

Post-extraction cleaning:
- Strip embedded amounts: `re.sub(r'\s*\(?\$?-?[\d,]+\.\d{2}\)?', '', desc)`
- Strip leading junk: `re.sub(r'^[|_\s]+', '', desc)`

`description` is the primary input for all `keyword_classify` normalizations
(`equipment_type`, `material`, `schedule`, `charge_type`/`charge_code`).

---

### 13. `charge_type`
**Level**: Charge
**Required**: No
**Source**: `keyword_classify` on `description` → used as input to `charge_normalize`

An **intermediate classification** field used only by patterns that employ
`charge_normalize`. It holds a vendor-internal label (e.g., `"Pickup"`, `"Haul"`,
`"Rental"`) that acts as the lookup key into `charge_code_map`.

Patterns that resolve `charge_code` directly via `keyword_classify` (without
`charge_normalize`) do not use `charge_type` and may leave it blank.

**Patterns using `charge_type` → `charge_normalize`**: Robinson Waste, Republic
Services, WM Invoice Detail, Ace Recycling, Burgmeier's, Athens, Cockey's Format A/B.

---

### 14. `charge_total`
**Level**: Charge
**Required**: Yes
**Source**: `charge_pipeline` → `charge_extract.amount_mode`

The dollar amount for this charge line. The extraction strategy is set by
`amount_mode`:

| Mode | Logic |
|------|-------|
| `last_is_total` *(default)* | Last amount on the line = `charge_total`; if ≥ 3 amounts: `[-3]` = qty, `[-2]` = unit_rate |
| `last3_qru` | Cockey's format: last = total, second-to-last = unit_rate, third-to-last = qty |

**Amount pre-cleaning** (applied before parsing):
- `"478 .32"` → `"478.32"` (space in decimal)
- `"-4,98"` → `"-4.98"` (comma-as-decimal separator)
- `"-$177.00"` → `"$-177.00"` (sign normalization for capture)
- `(amount)` → negative value (parenthesized negatives)

**Weight filter**: If `weight_pattern` matches, the tonnage value is removed from the
amount pool before `charge_total` is selected — prevents tonnage from being picked as
the charge amount.

---

### 15. `equipment_type`
**Level**: Charge
**Required**: No (but see build rules below)
**Source**: `keyword_classify` on `description` OR `service_line` inheritance

Canonical equipment class. Values:

| Value | Equipment |
|-------|-----------|
| `FRONT_LOAD` | Front-load dumpster |
| `CART` | Toter / wheeled cart / gallon-sized container |
| `ROLL_OFF` | Open-top roll-off (temp hauls) |
| `OPEN_TOP` | Permanent open-top (high-volume) |
| `COMPACTOR` | Stationary or self-contained compactor |
| `REAR_LOAD` | Rear-load dumpster |

**Two sourcing paths**:

1. **Direct**: `keyword_classify` reads `description` and matches keywords
   (e.g., `"front load"` → `FRONT_LOAD`, `"compactor"` / `"cmp"` → `COMPACTOR`).
   First match wins. Default applied when no keyword matches.

2. **Inherited**: For block-mode patterns (Robinson, Republic Services), a `service_line`
   regex extracts equipment type from a header line (e.g., `"8 YD FRONT LOAD MSW"`).
   Subsequent charge lines in that block inherit via `svc_ctx` propagation.
   `parent_container` then fills in any remaining orphans bidirectionally.

`equipment_type` feeds `charge_normalize` — it determines whether `Rental` resolves to
`Monthly Rental Commercial` vs. `Monthly Rental Industrial`.

**Build rules**:
- Every **service charge** (recurring or haul) must have `equipment_type` — it is the
  key input to `charge_normalize`. A service line with no `equipment_type` will produce
  a wrong or missing `charge_code`.
- **Surcharge/fee lines** (fuel, tax, admin) may have no direct `equipment_type` — they
  acquire it via `parent_container` inheritance. After `parent_container` runs, all
  non-zero charges should have `equipment_type` unless the vendor truly bills lump-sum
  surcharges without equipment context.
- Patterns without a `default` (rob_invoice, rs_invoice, ace_recycling, wm_invoice_detail,
  modern_disposal, uws_invoice, town_of_gilbert, ck_format_b) require that every service
  line keyword-match explicitly. A null `equipment_type` on a service line in these
  patterns is an **extraction gap** — add a keyword rule.
- `vanderlinde` defaults to an empty string (`""`), not `None` — treat as null.
- **Pattern default inventory**:

  | Default | Patterns |
  |---------|----------|
  | `FRONT_LOAD` | athens, aspen_waste, casella, city_of_oxnard, earthwise, edco_disposal, kmg_hauling, lepage, marborg, meridian_waste, nws, rumpke, sbc_waste, trashbilling_standard, usa_waste, waste_connections, waste_masters, waste_pro, wm_customer_id, zero_waste |
  | `ROLL_OFF` | 121_disposal, aaa_rubbish, checksammy, got_junk, tate_services, veit_disposal, waste_disposal_az |
  | none (explicit match required) | rob_invoice, rs_invoice, ace_recycling, wm_invoice_detail, modern_disposal, uws_invoice, town_of_gilbert, burgmeier, ck_format_b |

---

### 16. `equipment_size`
**Level**: Charge
**Required**: No
**Source**: `regex_capture` or `regex_parse_multi` on `description` or `service_line`

Container size with unit, as it appears on the invoice. Common forms:
- `"8 YD"`, `"2 YD"`, `"96 GAL"`, `"64 GAL"`, `"40 YD"`

Extracted via a vendor-specific size pattern (e.g., `(\d+(?:\.\d+)?)\s*(?:YD|GAL)`).
For block-mode patterns the size is pulled from the service header line and inherited.
Not normalized — raw OCR value is kept so the downstream weight calculation can apply
the correct density.

---

### 17. `material`
**Level**: Charge
**Required**: No (but see build rules below)
**Source**: `keyword_classify` on `description` (or `service_line` for block-mode)

The waste stream type. Canonical values used across patterns:

| Value | Stream |
|-------|--------|
| `Trash` | Municipal solid waste / general refuse |
| `MSW` | Municipal solid waste (used by some patterns — maps to Trash downstream) |
| `Recycling` | Commingled / single-stream recycling |
| `Single Stream` | Explicit single-stream recycling |
| `Cardboard` | OCC / corrugated cardboard |
| `OCC` | Cardboard (alternate label, used by wm_invoice_detail) |
| `Organics` | Food waste / organics |
| `Green Waste` | Yard debris / green waste |
| `C&D` | Construction and demolition debris |
| `Scrap Metal` | Metal / ferrous / non-ferrous |
| `Wood` | Wood waste |
| `Mattress` | Mattress disposal (Robinson only) |

Multi-word streams (e.g., `"Single Stream"`, `"Green Waste"`) are susceptible to OCR
column interleaving where Tesseract breaks the words across lines. Patterns address
this with multi-keyword rules where **all** component keywords must match anywhere in
the description.

**Build rules**:
- Every **service charge** must have a `material` value. A service row with no material
  cannot be weighted, reported, or categorized downstream.
- **Surcharge/fee lines** (fuel, tax, admin, rental fees) do not inherently carry
  material — they acquire it via `parent_container` inheritance from the nearest
  service charge in the same block. After `parent_container` runs, fee lines should
  have material unless the invoice is a lump-sum with no associated service line.
- Patterns with a keyword-only default (`MSW`, `Trash`) cover the common case but
  hide gaps — if a recycling line doesn't match a keyword, it silently becomes `MSW`.
  Review non-`MSW` patterns by cross-checking `material` against `charge_code`.
- Patterns with `default: None` (rob_invoice, rs_invoice, ace_recycling,
  wm_invoice_detail, modern_disposal, burgmeier, uws_invoice, athens,
  town_of_gilbert, ck_format_b) require every service line to keyword-match
  explicitly. Null material on a service charge in these patterns is an extraction
  gap — the keyword list is missing coverage for that description.
- **Pattern default inventory**:

  | Default | Patterns |
  |---------|----------|
  | `MSW` | 121_disposal, aaa_rubbish, aspen_waste, casella, checksammy, city_of_oxnard, earthwise, edco_disposal, got_junk, kmg_hauling, lepage, marborg, meridian_waste, nws, rumpke, sbc_waste, tate_services, trashbilling_standard, usa_waste, vanderlinde, veit_disposal, waste_connections, waste_disposal_az, waste_masters, waste_pro, wm_customer_id, zero_waste |
  | `Trash` | ck_format_b |
  | none (explicit match required) | rob_invoice, rs_invoice, ace_recycling, wm_invoice_detail, modern_disposal, burgmeier, uws_invoice, athens, town_of_gilbert |

---

### 18. `schedule`
**Level**: Charge
**Required**: No (but see build rules below)
**Source**: `keyword_classify` or `regex_parse_multi` on `description`

Pickup frequency. The field encodes whether the service is **recurring** (happens on a
fixed cadence) or **on-call** (triggered per request). This binary distinction drives
the weight calculation: recurring services get calculated weight (size × density ×
pickups); on-call services use actual weight from the invoice.

**On-call indicators** (service happens per request, no fixed cadence):

| Value | Patterns |
|-------|----------|
| `ON_CALL` | 121_disposal, sbc_waste, ace_recycling |
| `On Call` | rob_invoice, rs_invoice, meridian_waste, kmg_hauling |
| `MONTHLY` (for roll-off rental-only lines) | kmg_hauling, meridian_waste, sbc_waste |

**Recurring indicators** (fixed cadence — frequency determines weight):

| Format | Examples | Patterns |
|--------|----------|---------|
| `Weekly x{n}` | `Weekly x1` – `Weekly x6` | wm_customer_id, wm_invoice_detail, waste_masters, lepage, athens |
| `Monthly x{n}` | `Monthly x1` – `Monthly x6` | wm_customer_id, modern_disposal, waste_masters, lepage, usa_waste |
| `{n}X_WEEKLY` | `1X_WEEKLY`, `2X_WEEKLY`, `3X_WEEKLY` | kmg_hauling |
| `Every Other Week` | — | wm_customer_id, waste_masters |
| `Daily x1` | — | wm_invoice_detail |
| `MONTHLY` / `Monthly` | — | meridian_waste, sbc_waste, uws_invoice, kmg_hauling |

**Full value inventory** (all values in active use):
`ON_CALL`, `On Call`, `1X_WEEKLY`, `2X_WEEKLY`, `3X_WEEKLY`, `MONTHLY`, `Monthly`,
`Monthly x1`–`x6`, `Weekly x1`–`x6`, `Every Other Week`, `Daily x1`

> [!CAUTION]
> Two format conventions coexist: `Weekly x3` (WM/LePage style) and `3X_WEEKLY`
> (KMG style). If `schedule` is used in downstream joins or weight calculations,
> a normalization step is required before comparison.

**Key rule** (from LEARNINGS.md): bare `"weekly"` or `"monthly"` in a charge description
does NOT trigger a schedule value — only explicit markers like `"Weekly x3"` or
`"3x/week"` do. Exception: `wm_invoice_detail` uses bare `"weekly"` / `"monthly"` as
a fallback (`schedule_fallback`) for lines where no explicit multiplier appears.

**Build rules**:
- Every **service charge** should resolve to either on-call or a recurring frequency.
  A service charge with no schedule cannot be weighted downstream.
- **Surcharge/fee lines** do not carry their own schedule — they inherit from the
  nearest service charge via `parent_container`. After inheritance runs, fee lines
  should have a schedule that matches their parent service.
- When `charge_code` is `Empty & Return`, `Haul`, or `Disposal Charge`, schedule
  should be `ON_CALL` or `On Call`. If it is a recurring value, that is likely
  a classification error.
- When `charge_code` is `Monthly Service *` or `Monthly Rental *`, schedule should
  be a recurring value. If it is `ON_CALL`, that is likely a misclassification.
- **Pattern default inventory**:

  | Default | Patterns |
  |---------|----------|
  | `Monthly x1` | lepage, wm_customer_id, waste_masters, usa_waste, modern_disposal, athens |
  | `MONTHLY` | kmg_hauling, meridian_waste, sbc_waste |
  | `Monthly` | uws_invoice |
  | `ON_CALL` | 121_disposal |
  | none (explicit match required) | rob_invoice, rs_invoice, ace_recycling, wm_invoice_detail, burgmeier, ck_format_b |
  | no schedule logic (always null) | aaa_rubbish, aspen_waste, casella, checksammy, city_of_oxnard, earthwise, edco_disposal, got_junk, marborg, nws, rumpke, tate_services, trashbilling_standard, vanderlinde, veit_disposal, waste_connections, waste_disposal_az, waste_pro, zero_waste |

  Patterns with no schedule logic are typically single-vendor, single-service-type
  invoices where the schedule is implicit (e.g., all Tate Services invoices are
  roll-off pulls → always `ON_CALL`).

---

### 19. `charge_code`
**Level**: Charge
**Required**: Yes
**Source**: `keyword_classify` → `charge_code` directly, OR `charge_normalize`(`charge_type` + `equipment_type`)

The canonical charge code from `wasteology_ops.charge_code_ref` (160 active codes).
This is the final normalized value — what flows into the database.

**Two resolution paths**:

**Path A — Direct `keyword_classify`** (simpler patterns):
Keywords from `description` are matched directly to charge code labels.
Example: `"fuel surcharge"` → `"Environmental Surcharge"`.

**Path B — `charge_normalize`** (complex patterns: Robinson, Republic, WM, Ace, Burgmeier's, Athens, Cockey's):
1. `keyword_classify` sets `charge_type` (vendor label, e.g., `"Rental"`)
2. `equipment_type` is looked up in `equipment_class_map`:
   - `FRONT_LOAD`, `REAR_LOAD`, `CART` → `"commercial"`
   - `OPEN_TOP`, `COMPACTOR` → `"industrial"`
3. `charge_type` is looked up in `charge_code_map`:
   - If the value is a string → used directly
   - If the value is a dict → branches on `eq_class`

```
charge_type="Rental" + equipment_type="COMPACTOR"
  → eq_class = "industrial"
  → charge_code = "Monthly Rental Industrial"

charge_type="Rental" + equipment_type="FRONT_LOAD"
  → eq_class = "commercial"
  → charge_code = "Monthly Rental Commercial"
```

`charge_normalize` runs **after** `parent_container`, ensuring equipment_type is
resolved on all charges (including fee/surcharge lines) before the code is assigned.
`renormalize_codes` re-runs `charge_normalize` on the full charge list after
`parent_container` has propagated inherited fields, catching any codes that were set
before equipment context was available.

**Common codes across all patterns**:

| Code | When Used | Implied Schedule | Implies Equipment |
|------|-----------|-----------------|-------------------|
| `Monthly Service Commercial` | Recurring front-load / cart pickup | Recurring | FRONT_LOAD / CART / REAR_LOAD |
| `Monthly Service Industrial` | Recurring compactor service | Recurring | COMPACTOR |
| `Monthly Rental Commercial` | Container rental (commercial) | Recurring | FRONT_LOAD / CART |
| `Monthly Rental Industrial` | Container rental (industrial) | Recurring | OPEN_TOP / COMPACTOR |
| `Empty & Return` | Roll-off haul (dump and return) | On Call | ROLL_OFF / OPEN_TOP |
| `Haul` | Generic roll-off pull | On Call | ROLL_OFF / OPEN_TOP |
| `Disposal Charge` | Per-ton or per-haul disposal | On Call | any |
| `Delivery Commercial` | Container drop-off (commercial) | On Call | FRONT_LOAD / CART |
| `Delivery Industrial` | Container drop-off (industrial) | On Call | OPEN_TOP / COMPACTOR |
| `Extra Pick Up` | Non-scheduled additional pickup | On Call | any |
| `Trip Charge` | Dry run / push-out / pull-out | On Call | any |
| `Final Pick Up` | Container removal / last service | On Call | any |
| `Environmental Surcharge` | Fuel, energy, environmental fees | inherited | inherited |
| `FUEL SURCHARGE` | Fuel surcharge (WM format) | inherited | inherited |
| `Local Surcharge Commercial` | City/franchise/administrative fees | inherited | inherited |
| `Administrative Fee` | Admin fee | inherited | inherited |
| `Franchise Fee` | Municipal franchise fee | inherited | inherited |
| `Tax Commercial` | Sales or utility tax | inherited | inherited |
| `Vendor Late Fees` | Late payment fees | inherited | inherited |
| `Overage` | Excess yardage | inherited | inherited |
| `Contaminated Load` | Contaminated material rejection | inherited | inherited |
| `Miscellaneous` | Catch-all for uncategorized charges | inherited | inherited |

**Build rules**:
- `charge_code` is **required** on every charge row. A null `charge_code` means either
  the `keyword_classify` rules didn't match (add a rule) or `charge_normalize` received
  a `charge_type` value not in the `charge_code_map` (add the entry).
- `charge_code` and `schedule` must be consistent: `Empty & Return`, `Haul`,
  `Disposal Charge`, `Delivery *`, `Extra Pick Up`, `Trip Charge`, and `Final Pick Up`
  should always pair with an on-call schedule. `Monthly Service *` and
  `Monthly Rental *` should always pair with a recurring schedule. A mismatch is a
  classification error in either field.
- `charge_code` and `equipment_type` must be consistent: `Monthly Service Commercial`,
  `Monthly Rental Commercial`, `Delivery Commercial` should only appear with
  `FRONT_LOAD`, `CART`, or `REAR_LOAD`. Industrial codes should only appear with
  `OPEN_TOP` or `COMPACTOR`. Cross-class combinations indicate a `charge_normalize`
  misconfiguration or missing equipment keyword.
- Surcharge/fee codes (`Environmental Surcharge`, `Tax Commercial`, etc.) should never
  be the only code on an invoice — they only make sense alongside a service charge.
  A surcharge appearing without a parent service charge is a structural extraction gap.

---

### 20. `weight`
**Level**: Charge
**Required**: No
**Source**: `charge_extract.weight_pattern` or `multi_heuristic.weight_pattern`

Actual tonnage from the invoice, applicable to roll-off and compactor pulls.
Extracted by a vendor-specific regex from the charge line text before amounts are
selected (tonnage values are removed from the amount pool to prevent them from being
picked as `charge_total`).

Stored as a `float`. Only present when the vendor includes weight on the invoice line.

---

### 21. `weight_unit`
**Level**: Charge
**Required**: No
**Source**: Set to `"TONS"` automatically when `weight` is extracted

Always `"TONS"` when populated. No other unit is produced — vendor weight values are
normalized to tons at extraction time.

---

### 22. `flag`
**Level**: Computed
**Required**: Yes
**Source**: `validate()` → semicolon-joined list

All validation issues found for this invoice, joined with `"; "`. Empty string when
the invoice passes all checks.

| Flag | Condition |
|------|-----------|
| `HDR_MISSING: {field}` | A required header field is null/empty after extraction |
| `CHG_MISSING[{i}]: {field}` | Charge `i` is missing a required charge field |
| `DIFF: charge_sum != {total_field} (diff={n})` | `abs(bill_total - charge_sum) >= $0.02` |
| `NO_CHARGES` | The charge pipeline returned an empty list |

Multiple flags on the same invoice are concatenated:
```
HDR_MISSING: invoice_number; DIFF: charge_sum != bill_total (diff=12.50)
```

The tracker maps flags to a `status` field:
- `VALID` — no flags
- `UNDER_CAPTURE` — positive diff (charges missed)
- `DIFF` — negative diff (over-captured)
- `UNVALIDATED` — `bill_total` missing/garbled
- `NO_PATTERN` — no routing regex matched (row not written to vendor extract)

---

## Vendor-Specific Extended Fields

Appended after column 22, never inserted between canonical columns.

| Field | Vendors | Description |
|-------|---------|-------------|
| `wo_number` | Robinson Waste, Cockey's | Work order number from charge line |
| `site_id` | Cockey's Format A/B | Site/location identifier from block header |
| `qty` | Multiple | Number of units (lifts, tons, containers) |
| `unit_rate` | Multiple | Per-unit rate (charge_total / qty) |
| `reference` | Some patterns | Internal billing reference from charge line |

---

## Validation Rules Summary

### Runtime (enforced by `validate()`)

| Check | Threshold | Flag Produced |
|-------|-----------|---------------|
| Header required fields present | All must be non-null | `HDR_MISSING: {field}` |
| Charge required fields present | `charge_total` non-null on every charge | `CHG_MISSING[i]: charge_total` |
| Charge sum matches bill_total | `abs(diff) < $0.02` | `DIFF: charge_sum != bill_total (diff=n)` |
| At least one charge extracted | `len(charges) > 0` | `NO_CHARGES` |

`charge_sum_check: false` is set only on `trashbilling_standard` — that format does
not produce individual charge amounts, so sum validation is meaningless and `valid`
is always `None`.

---

### Pattern Build Rules (enforced by review, not runtime)

These are correctness invariants to check during gate review. The executor does not
raise flags for them — they surface as unexpected values in the review CSV.

**Every service charge must have**:
- `material` — null material on a service line is a keyword coverage gap
- `equipment_type` — null equipment on a service line breaks `charge_normalize`
- `charge_code` — null charge_code means a classify rule or charge_code_map entry is missing
- `schedule` — null schedule means the charge cannot be weighted downstream

**Surcharge/fee lines** (charge_code in `Environmental Surcharge`, `FUEL SURCHARGE`,
`Local Surcharge Commercial`, `Administrative Fee`, `Franchise Fee`, `Tax Commercial`,
`Vendor Late Fees`, `Finance Charge`) may have null `material`, `equipment_type`,
and `schedule` **before** `parent_container` runs. After `parent_container`, they
should inherit all four from the nearest service charge. If still null after
inheritance, the invoice has no associated service charge — flag for review.

**Cross-field consistency**:

| If `charge_code` is… | `schedule` should be… | `equipment_type` should be… |
|---|---|---|
| `Monthly Service Commercial` | recurring (any `Weekly x{n}` / `Monthly x{n}`) | `FRONT_LOAD`, `CART`, or `REAR_LOAD` |
| `Monthly Service Industrial` | recurring | `COMPACTOR` |
| `Monthly Rental Commercial` | recurring | `FRONT_LOAD` or `CART` |
| `Monthly Rental Industrial` | recurring | `OPEN_TOP` or `COMPACTOR` |
| `Empty & Return` | `On Call` or `ON_CALL` | `ROLL_OFF` or `OPEN_TOP` |
| `Haul` | `On Call` or `ON_CALL` | `ROLL_OFF` or `OPEN_TOP` |
| `Disposal Charge` | `On Call` or `ON_CALL` | any |
| `Delivery Commercial` | `On Call` or `ON_CALL` | `FRONT_LOAD` or `CART` |
| `Delivery Industrial` | `On Call` or `ON_CALL` | `OPEN_TOP` or `COMPACTOR` |

A mismatch in either column indicates a classification error — fix in the keyword
rules or `charge_code_map`, not in the data.

**Schedule format normalization** (not enforced at runtime):
`3X_WEEKLY` (KMG style) and `Weekly x3` (WM/LePage style) are both in active use and
represent the same cadence. Any downstream join on `schedule` must normalize these
before comparing.

---

*See also: `ARCHITECTURE.md` (executor design), `patterns/LEARNINGS.md` (OCR conventions), `PATTERN_BUILD_PROCESS.md` (gate process)*
