# Pattern Build Learnings

## Tesseract OCR Conventions

Tesseract produces different whitespace than Document AI:

| Element | Document AI | Tesseract |
|---------|------------|-----------|
| Field separators | `\n` between fields | `\s+` (space or newline) |
| Block terminators | `KEYWORD\n` | `KEYWORD\s+` |
| Page headers | `PAGE\n\d+\n` | `PAGE\s+\d+\s*\n` |

**Rule: Always use `\s+` instead of `\n` in extraction patterns.** Never assume newline-delimited fields.

---

## OCR Column Interleaving

Tesseract splits compound terms across lines when OCR columns interleave:

```
Single          →  "Single"
/ Stream        →  "/ Stream"
Recyclin        →  "Recyclin"
g               →  "g"
```

**Fix:** Use `COMPOUND_MATERIALS` in transform_rules config. If all component words appear anywhere in the chunk, resolve to the compound name. Don't rely on single-regex matching for multi-word materials.

---

## Columnar OCR Separation

On some multi-column invoices, Tesseract reads column-by-column instead of row-by-row. Descriptions end up in one block, amounts in another, with no inline pairing:

```
[DESCRIPTION block]     [QTY block]      [AMOUNT block]
Dump & Return W.0#..   PO.#3635761      $150.00
MSW - Disposal          78-1114041       $52.00
```

This is a structural OCR failure — a different problem from garbled text. When detected, it requires the `column_positional` handler to zip descriptions and amounts by position.

If a format consistently produces columnar separation, it may need its own pattern record (different from the same vendor's inline format).

---

## Qty Cap

WM pickup quantities are small integers (0-7 typical). Dollar amounts after material words in descriptions also match qty patterns (e.g., `Recycling 30.77`).

**Fix:** Cap qty at 15. Values > 15 are dollar amounts leaking from OCR columns.

---

## Schedule Inheritance

Bare `Weekly` or `Monthly` in description text does not indicate pickup frequency. Only explicit markers do.

**Fix:** Only match `(Weekly|Monthly|Daily)\s*x\s*(\d+)`. Bare keywords return None — `parent_container` handler inherits from parent charge.

---

## Bidirectional Parent Container

Some locations have ancillary charges (surcharges, CRC fees) appearing BEFORE the parent Pickup charge in OCR output.

**Fix:** `parent_container` handler looks backward first, then forward within the same block. Orphans inherit equipment_type, equipment_size, material, schedule from nearest parent in either direction.

---

## Amount Heuristic Priority

The `multi_heuristic` handler tries strategies in strict order:
1. **Credit** — any negative → charge_total
2. **Triplet** — price + tax = total (within $0.02)
3. **Per-ton** — rate × qty = total (disposal charges)
4. **Fallback** — last non-zero amount

Weight and qty MUST be extracted first and filtered from the amount pool. Otherwise tonnage values (e.g., 1.06 from `1.06Tons`) get picked as charge_total.

---

## Charge Code Normalization (pattern-level)

Uses the `charge_normalize` handler inside each pattern's `transform_rules`. Equipment-class-dependent:

- **commercial** (FRONT_LOAD, REAR_LOAD, CART): maps to Commercial variants
- **industrial** (OPEN_TOP, COMPACTOR): maps to Industrial variants

The `charge_normalize` handler runs AFTER `parent_container` so equipment_type is resolved on all charges before mapping. Both `charge_code_normalize` and `renormalize_after_parent` rules must be kept in sync — they share the same `charge_code_map` structure.

---

## Validation

`charge_sum == invoice_total` is the primary validation. Sum of all charge_total values must equal the header's invoice total within $0.02.

- Small diffs ($1-$6): typically OCR noise — garbage amounts from garbled page transitions
- Large diffs: structural extraction failure (missed blocks, missed chunks)
- The diff is always surfaced in the `flag` column. Never silently absorbed.

---

## Robinson-Specific: Past-Due Invoice Footer

Robinson invoices with past-due balances have this footer structure:

```
INVOICE
TOTAL .              ← OCR garbles the current-period total
AGE CURRENT  31-60   61-90   OVER 90   PLEASE PAY
AMOUNT $X.XX  $X.XX  $X.XX   $X.XX     $total
```

- `AMOUNT DUE` in the header = full balance including past due
- `INVOICE TOTAL` = current period only, but OCR garbles it to "." or noise
- The CURRENT amount (first value in the AMOUNT row) = actual invoice total
- `PLEASE PAY` amount = `AMOUNT DUE` (total balance)

---

## Charge Code Normalization (executor.py)

Added in session 2025-03-30. All normalization logic lives in executor.py, loaded at startup.

### charge_code_ref.csv (rebuilt)
- Unified reference: 171 canonical codes, replaces old 18-row headerless file
- New columns: `charge_code_id, charge_code, classification, second_attribute, is_active, tier`
- Tier 1 (18 codes) = preferred/high-priority; Tier 2 (153) = standard

### charge_code_aliases.json (new)
- Maps non-canonical codes → canonical codes
- Equipment-class-aware entries use `{"FRONT_LOAD": "...", "COMPACTOR": "...", "default": "..."}`
- Loaded at startup; applied in `_normalize_charge_codes()`

### Per-charge flags
| Flag | Meaning |
|------|---------|
| `HITL:NO_CHARGE_CODE` | Charge has no code — needs human review |
| `HITL:charge_code=X` | Code extracted but not in canonical set |
| `NO_SCHEDULE` | Recurring container service charge with no pickup schedule |
| `NO_TONNAGE` | Roll-off/compactor disposal charge (`Disposal Charge`, `Disposal`, `Disposal Charge Special Waste`) with no weight |

### NO_SCHEDULE logic
- Only fires when **all three** conditions are true:
  1. `charge_code` is in `_PICKUP_SERVICE_CODES` (actual pickup codes only — not rentals/fees)
  2. `equipment_type` is in `_RECURRING_EQUIPMENT` (`FRONT_LOAD`, `CART`, `REAR_LOAD`)
  3. `schedule` is empty
- Roll-offs and compactors are on-demand — never flagged NO_SCHEDULE
- Rentals, surcharges, taxes, lock bars hung to the same container — never flagged NO_SCHEDULE
- **The schedule belongs to the container, not the charge.** All charges on a container inherit the container's pickup schedule. Only the service charge (the pickup event) requires one.

### Schedule canonical values
| Value | Meaning |
|-------|---------|
| `Weekly x1` … `Weekly x6` | N pickups per week |
| `Weekly x12` | 12x/week (e.g. daily + Saturday) |
| `Biweekly` | Every other week |
| `Monthly x1` | Once per month (must appear in OCR — not a default) |
| `ON_CALL` | On-demand / roll-off / compactor |

`MONTHLY` is **not** a schedule. `Monthly` alone is **not** a schedule. Only `Monthly x1` is valid, and only when explicitly printed on the invoice.

---

## Schedule Extraction by Vendor

### Vendors where pickup schedule IS on the invoice
| Vendor | Format | Pattern key |
|--------|--------|-------------|
| Athens | `#P/U: N` or `# P/U: N` | `schedule_detect` (keyword `p/u` + count) |
| Meridian Waste | `#P/U: N` | `schedule_detect` (keyword `p/u` + count) |
| WM Invoice Detail | `Weekly xN` / `Monthly xN` in description | `schedule_extract` (regex_parse_multi) |
| WM Customer ID | `N Time Per Week` in description | `schedule_detect` (keyword array) |
| Rumpke | `P/U: N` in description | `schedule_extract` (regex_parse_multi) |
| Casella | `NX MTH` in description | `schedule_monthly_extract` |
| Lepage | `#P/U: N` | `schedule_detect` |
| KMG Hauling | `Nx/week` | `schedule_detect` |
| SBC Waste | keyword-based | `schedule_detect` |
| Modern Disposal | `Weekly` / `Every 2 Weeks` | `schedule_detect` |
| Earthwise | `NXS PER WEEK` | `schedule_extract` |
| City of Oxnard | `XN` prefix | `schedule_extract` |
| Trashbilling | `NXW` | `schedule_extract` |

### Vendors where pickup schedule is NOT printed
Ace Recycling, UWS, Town of Gilbert, EDCO Disposal, Rob Invoice, NWS, Waste Pro, USA Waste, Aspen Waste, Zero Waste, SBC Waste, WM Customer ID (partial), Lepage (partial)

These generate NO_SCHEDULE flags on service charges — expected, not an extraction failure.

### Complete pattern changes — schedule extraction added (2025-03-30)

| Pattern | Rule added | What it extracts |
|---------|-----------|-----------------|
| `rumpke` | `schedule_extract` (regex_parse_multi) | `P/U: N` → `Weekly xN` |
| `casella` | `schedule_monthly_extract` | `NX MTH` → `Monthly xN` |
| `casella` | `schedule_eow` | `eow` keyword → `Biweekly` |
| `earthwise` | `schedule_extract` | `NXS PER WEEK` → `Weekly xN` |
| `city_of_oxnard` | `schedule_extract` | `XN` prefix → `Weekly xN` |
| `trashbilling_standard` | `schedule_extract` | `NXW` → `Weekly xN` |
| `marborg` | fixed `schedule_extract` | `regex_capture` → `regex_parse_multi` with format template |
| `athens` | `schedule_detect` | `p/u: N` → `Weekly xN` (colon-anchored) |
| `meridian_waste` | `schedule_detect` | `p/u: N` → `Weekly xN` (colon-anchored) |
| `modern_disposal` | `schedule_detect` | `Weekly` → `Weekly x1`; `Every 2 Weeks` → `Biweekly` |
| `rumpke`, `casella`, `earthwise`, `city_of_oxnard`, `trashbilling_standard`, `vanderlinde`, `veit_disposal`, `waste_pro`, `waste_connections`, `nws`, `aspen_waste`, `zero_waste`, `edco_disposal`, `rob_invoice`, `ck_format_b`, `wm_invoice_detail` | `schedule_oncall` | `OPEN_TOP`/`COMPACTOR` equipment_type → `ON_CALL` |

### Complete pattern changes — MONTHLY removed (2025-03-30)

The following patterns had `default: "MONTHLY"`, `default: "Monthly x1"`, or equipment-type rules mapping `FRONT_LOAD`/`CART`/`REAR_LOAD` → `MONTHLY` removed:

`121_disposal`, `ace_recycling`, `aspen_waste`, `athens`, `burgmeier`, `ck_format_b`, `edco_disposal`, `kmg_hauling`, `lepage`, `meridian_waste`, `modern_disposal`, `nws`, `rob_invoice`, `sbc_waste`, `town_of_gilbert`, `trashbilling_standard`, `uws_invoice`, `usa_waste`, `waste_connections`, `waste_masters`, `waste_pro`, `wm_customer_id`, `wm_invoice_detail`, `zero_waste`

Rule: **Never default schedule to MONTHLY or Monthly x1.** If not in OCR, leave empty.

### `#P/U:` extraction — digit disambiguation

Athens and Meridian encode pickup frequency as `#P/U: 3` or `# P/U: 3`. The count digit must be matched as `"p/u: N"` (colon included), **not** as `["p/u", "N"]` (two separate keywords).

**Why:** `keyword_classify` checks if ALL keywords are substrings of the (lowercased) source. A description like `"4YD-ORGANICS BIN # P/U: 3"` contains both `"4"` (from container size) and `"p/u"`, so `["p/u", "4"]` fires before `["p/u", "3"]`, producing `Weekly x4` instead of `Weekly x3`.

**Fix:** Use `"p/u: 3"` as a single keyword. The colon anchors the match immediately after `P/U`, excluding container size digits.

```json
{"keywords": "p/u: 3", "label": "Weekly x3"},
{"keywords": "p/u: 2", "label": "Weekly x2"},
{"keywords": "p/u:",   "label": "Weekly x1"}
```

---

### Equipment-based defaults (all vendors)
- `OPEN_TOP` / `COMPACTOR` → `ON_CALL` (set via `schedule_oncall` keyword_classify on `equipment_type`)
- Do NOT default FRONT_LOAD/CART/REAR_LOAD to any value — leave empty if not in OCR

---

## WM Invoice Detail: Charge Code Fixes

WM descriptions not caught by the original `charge_code_map` — added to both
`charge_code_normalize` and `renormalize_after_parent` maps:

| Description keyword | charge_type label | Canonical code |
|--------------------|-------------------|----------------|
| `landfill` | Landfill Fee | Local Surcharge Commercial |
| `franchise` | Franchise Fee | Franchise Fee Commercial |
| `govt fran` | Franchise Fee | Franchise Fee Commercial |
| `contamination` | Contamination | Contaminated Load |
| `inactivity` | Inactivity | Inactivty Fee |
| `ab939` | Ab939 Fee | Local Surcharge Commercial |
| `relocation` | Relocation | Relocate Commercial / Relocate Industrial (equipment-aware) |
| `recycle material offset` | Recycle Material Offset | Recycling Offset |

### WM `Weekly x0` fix
Pattern: `x\s*(?P<mult>[0-9l]+)` was matching `x0` from `x0.5` (biweekly descriptions).
Fix: Added negative lookahead `(?!\.\d)` to prevent matching fractional values.

---

## Service Address Extraction (2026-03-30)

`service_address` is a required header field on every pattern. Coverage target: ≥95% per vendor.
Final corpus coverage: **98.3%** across 1,385 invoices (37 patterns).

### Design Rules

1. **Every pattern must have at least one `service_address` extraction stage.** No pattern ships without it.
2. **Use `skip_if_set: ["service_address"]` on all fallback stages** — so a successful primary extraction is never overwritten by a weaker fallback.
3. **The `addr_concat` transform overwrites `service_address`.** If you use `addr_concat` (concat_fields on street + city → service_address) in `execution_plan`, any fallback captured directly into `service_address` during extraction will be erased.

### addr_concat Overwrite Problem

`execution_plan` transforms run AFTER `extraction_stages`. A fallback that sets `service_address` directly during extraction will be overwritten by `addr_concat` if street/city are empty (producing an empty string).

**Fix pattern for fallbacks when addr_concat is in the execution plan:**

```json
// Extraction stage — capture into intermediate field, not service_address directly
{
  "name": "service_address_fallback",
  "method": "search",
  "pattern": "(?P<fallback_addr>CUSTOMER_NAME\\s+C/O\\s+BILLING_COMPANY)",
  "flags": ["IGNORECASE"],
  "field_map": {"fallback_addr": "_fallback_addr"},
  "skip_if_set": ["service_street"]
}

// execution_plan
["bill_total_parse", "date_format", "addr_concat", "fallback_copy"]

// transform_rules
"fallback_copy": {
  "type": "copy_if_null",
  "source_field": "_fallback_addr",
  "target_field": "service_address"
}
```

The `copy_if_null` handler runs after `addr_concat` and only writes to `service_address` when it's still empty.

### Fallback Chain Pattern

When a vendor has multiple address formats, chain stages with `skip_if_set`:

```json
// Stage 1 (primary) — most common format
{
  "name": "service_address",
  "method": "search",
  "pattern": "WASTE\\s+HARMONICS\\s+(?P<service_address>\\d+[^\\n]+)",
  "flags": ["IGNORECASE"],
  "field_map": {"service_address": "service_address"}
}

// Stage 2 (fallback A) — fires only if stage 1 found nothing
{
  "name": "service_address_interleaved",
  "method": "search",
  "pattern": "7665[^\\n]+?(?P<service_address>\\d{4,5}\\s+[A-Z][^\\n]+)",
  "flags": ["IGNORECASE"],
  "field_map": {"service_address": "service_address"},
  "skip_if_set": ["service_address"]
}

// Stage 3 (fallback B) — last resort
{
  "name": "service_address_account_anchor",
  "method": "search",
  "pattern": "Service\\s+Location[^\\n]+\\nAcct\\s+#\\S+\\s+(?P<service_address>\\d+[^\\n]+)",
  "flags": ["IGNORECASE"],
  "field_map": {"service_address": "service_address"},
  "skip_if_set": ["service_address"]
}
```

### Address Patterns by Vendor Class

| Pattern | Primary anchor | Notes |
|---------|---------------|-------|
| WM Invoice Detail | `block_context` per location block | Multi-site: address extracted per block. Use `(?!\d)[^\n]*\n` (not `[^\d\n]`) — blank lines between `/` anchor and street number must be traversable |
| WM Customer ID | `Customer Name[^,\n]*(?:,[^\d,\n][^,\n]*)?,\s*(?P<service_address>\d+[^,\n]+)` | Allows 1–2 company suffix segments before street number |
| Republic Services | `Customer\s+Name[^\d\n]*(?P<service_address>\d+[^\n]+?)` + fallback | `[^\d\n]*` skips company suffix words |
| Cockey's (ck_format_b) | `Site\s+\d+\s*-\s*CUSTOMER\s+NAME\s*-\s*(?:[^-\n]+-\s*){0,5}(?P<service_address>\d+...)` | 0–5 dash-segments between customer name and street number (0 handles direct address format) |
| Robinson Waste | `site_line` service pattern with inherited address per block | Per-service address from line header |
| Athens, UWS, Meridian | `Customer Name[^\n]*\n(?P<service_address>\d+[^\n]+)` | Address on next line after customer name |
| LePage & Sons | `COMPANY\s+(?P<service_address>\d+[^\n]+)` + interleaved fallback | OCR column interleaving can merge billing company PO address with service address on same line |
| EDCO Disposal | Anchored to `BALANCE FORWARD`/`MO DAY` section, skipping payment lines | Vendor's own address appears in header — must anchor to body section |
| Waste Disposal AZ | `addr_concat` (street + city) + `copy_if_null` fallback from customer name | Some invoices have no printed address — use customer name as fallback |

### Known Structural Gaps (not fixable by pattern)

| Pattern | Gap | Invoices | Reason |
|---------|-----|----------|--------|
| `edco_disposal` | 82% | 3 | Roll-off invoices with no service address printed |
| `ace_recycling` | 94% | 6 | UTSL01 site invoices with no address line printed |

All other 35 patterns are at 100%. These 9 are data gaps in the source PDFs — not extraction failures. Accept as-is.

**Overall corpus coverage: 99.4% (1,376/1,385 invoices)**

---

## Build Order (by invoice count)

| # | Vendor | Count | Status |
|---|--------|-------|--------|
| 1 | Waste Management | 279 | Python script built (needs JSON conversion) |
| 2 | Cockey's | 173 | Python script built (needs JSON conversion) |
| 3 | Republic Services | 140 | Python script built (needs JSON conversion) |
| 4 | Robinson Waste | 113 | Python script built (needs JSON conversion) |
| 5 | Ace Recycling | 100 | Not started |
| 6 | Burgmeier's | 82 | Not started |
| 7 | Athens Services | 56 | Not started |
| 8 | Universal Waste Systems | 42 | Not started |
