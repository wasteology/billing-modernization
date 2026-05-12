# Pattern Build Process

---

## Inputs

Two things are needed to build a pattern:

1. **Raw OCR text** — from `output/ocr_results.csv`, the Tesseract output for each invoice
2. **Source PDF** — the original invoice, for visual reference when the OCR is ambiguous

The pattern is built by reading both. Once the pattern is locked, future processing uses OCR text only — no PDF access required.

---

## Output

Each pattern produces:

1. **Pattern JSON** — `patterns/json/{format_label}.json`
2. **Vendor extract CSV** — `output/vendor_extracts/{format_label}.csv` with all successfully processed invoices

---

## The Rolling Review CSV

One CSV per pattern being built:
```
output/review_{format_label}.csv
```

Every test run appends. Never overwrites. Columns:

| Column | Source |
|--------|--------|
| `run` | Auto-increment per run |
| `md5` | `md5(raw_ocr_text)` |
| `pdf_link` | `file:///` + corrected pdf_path |
| `pdf_filename` | From ocr_results.csv |
| Header fields | `invoice_date`, `account_name`, `invoice_number`, `bill_total` |
| Computed | `charge_sum`, `num_charges`, `valid`, `diff` |
| Charge fields | `service_date`, `description`, `charge_type`, `charge_total`, `equipment_type`, `equipment_size`, `material`, `schedule`, `charge_code`, `weight`, plus vendor-specific |
| `flag` | Auto-generated validation flags (empty = clean) |

---

## The Process (4 Stops)

### Stop 1 — Route + Extract Headers

CC builds `routing_regex` and `extraction_stages` in the pattern JSON, runs against 5 diverse sample invoices.

Shows: match count on corpus + extracted header values (invoice_number, invoice_date, bill_total, account_number, **service_address**) for the 5 samples.

**`service_address` is required.** Every pattern must include at least one extraction stage for it before Stop 1 is approved. If the primary pattern doesn't cover all invoice variants, add fallback stages with `skip_if_set: ["service_address"]`. See `patterns/LEARNINGS.md` — "Service Address Extraction" for design rules and the `addr_concat` overwrite pattern.

**User approves or corrects.**

### Stop 2 — Raw Blocks + Proposed Transforms

CC dumps one raw line-item block from each of the 5 samples AND proposes the `execution_plan` + `transform_rules` + `charge_pipeline` config.

**User describes the line item rules** (charge structure, what fields mean, edge cases) and approves/modifies the proposed transforms.

> [!CAUTION]
> CC proposes transforms based on the universal output spec (see CLAUDE.md). CC does NOT infer line item parsing rules from OCR alone — the user describes how charges work for this vendor.

### Stop 3 — 5 Invoices End-to-End

CC runs the full pipeline on 5 samples, writes results to the review CSV.

User opens the CSV and reviews. Feedback → CC adjusts pattern JSON and reruns. New results append with the next run number.

User says: **"done, go test on the rest."**

### Stop 4 — Full Corpus

CC runs the pattern against all invoices matching `routing_regex`.

Two outcomes:
- Issues found → CC reports stats + flagged rows. User reviews. Back to Stop 3 for targeted fixes.
- Clean → User confirms. Review CSV is wiped. Pattern is locked. Vendor extract CSV is generated.

---

## Auto-Validation Flags

Every review CSV row has a `flag` column. Empty = clean.

**Header-level:**
- `HDR_MISSING: invoice_number`
- `HDR_MISSING: bill_total`

**Charge-level:**
- `CHG_MISSING: equipment_type`
- `CHG_MISSING: material`
- `CHG_MISSING: charge_total`

**Validation:**
- `DIFF: charge_sum != bill_total (diff=X.XX)`
- `NO_CHARGES` — no charge lines extracted

---

## The Line Item Rule Gate (Stop 2)

CC dumps raw blocks from OCR:

```
--- RAW BLOCK (Serv #001 Roll Off Permanent 1 - 30YD) ---
02 - Oct Dump & Return W.O# 376700 1.00 $125.00 $125.00
02 - Oct  MSW - Disposal 01-4469278 $41.76
--- END BLOCK ---
```

User reads it and tells CC the rules:
- "First amount after description is qty"
- "Last amount is charge total"
- "MSW - Disposal lines have weight in tons when present"

CC translates user rules into `transform_rules` config. Not the other way around.

---

## Universal Output Spec

CC does not ask what fields to extract. Every pattern extracts the same core fields (defined in CLAUDE.md):

- **Required header**: `invoice_number`, `bill_total`, `account_number`, `service_address`
- **Required charge**: `service_date`, `description`, `charge_total`
- **Standard**: `invoice_date`, `equipment_type`, `equipment_size`, `material`, `schedule`, `weight`, `charge_code`, `charge_type`
- **Vendor-specific** (optional): `location_subtotal`, `site_id`, `wo_number`, `qty`, `unit_rate`

---

## Upstream Fix Rule

If a data issue surfaces at a later stop, fix at the source:

- Bad OCR → review queue, not regex workaround
- Header extraction miss → fix `extraction_stages`, not `transform_rules`
- Charge amounts don't sum → fix extraction or amount heuristic, not validation tolerance

---

## What CC Never Does

- Never infers line item rules from OCR without user describing them
- Never runs more than 5 invoices without a review checkpoint
- Never moves to the next pattern until user confirms the current one is clean
- Never modifies a locked pattern to handle a new format variant — that's a new pattern record
- Never writes vendor-specific code in the executor
- Never builds a standalone Python script instead of a pattern JSON record

---

## End-to-End Workflow

For each vendor format:

1. **Build** — Work through the 4 stops until the pattern is complete and locked
2. **Process** — Run all matching invoices through the locked pattern → `output/vendor_extracts/{format_label}.csv`
3. **Update tracker** — `output/invoice_tracker.csv` with results

The tracker is the single source of truth for pipeline status across all vendors.
