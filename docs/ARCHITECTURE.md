# Invoice Executor — Architecture

## Core Principles

1. **Infrastructure as code.** Pattern records are JSON data that map 1:1 to the `ip_vendor_pattern_bulk` database table. The executor is a thin runtime that reads a pattern record and processes any invoice matching it. All vendor-specific knowledge lives in the pattern record — never in executor code.

2. **Pattern isolation.** One pattern record = one invoice document format = one discrete processing path. A vendor with two invoice layouts gets two records. They share nothing except `vendor_name`. The executor never merges, blends, or falls back between patterns. An invoice matches one `routing_regex` or it fails to the unknown queue.

3. **Thin executor.** The executor is a fixed set of handler types. It has no knowledge of any vendor. No `if vendor_name == "..."`. No hardcoded field names. No decisions. Every decision is encoded in the pattern record. If a new vendor needs behavior the handlers can't express, the handler registry is extended — not the pattern record format.

4. **Deterministic always.** No confidence intervals. No probabilistic matching. No dark failures. A field is extracted or it isn't. A charge sum balances or the invoice fails. Every failure is surfaced with a reason. Every success is verifiable.

5. **Extract as-is, transform to spec.** Invoices are parsed/extracted exactly as they appear in the OCR text. The executor then transforms/normalizes the raw extracted values to match one unified `output_spec` with canonical field names. Extraction is faithful to the source. Transformation is faithful to the schema.

6. **Fix upstream, not downstream.** Data issues that propagate into later stage gates are fixed at the source. No bandaids for bad OCR, no workarounds for garbled fields. The pattern must work on hundreds of invoices of the same format. If OCR is broken, the invoice goes to the review queue — it does not get patched in a later transform.

7. **One format at a time.** Patterns are built sequentially, one invoice document format per build cycle. A new format is its own discrete pattern record. Multi-format handling within the same record is a violation.

---

## The Database Table

Pattern records are stored in `ip_vendor_pattern_bulk`:

| Column | Type | Purpose |
|--------|------|---------|
| `bulk_pattern_id` | PK | Auto-increment identifier |
| `vendor_name` | text | Canonical vendor name |
| `format_label` | text | Unique format identifier (e.g., `wm_invoice_detail`, `rob_roll_off`) |
| `routing_regex` | text | Lightweight regex to identify this format from raw OCR |
| `routing_priority` | int | Tie-breaker when multiple patterns match (lower = higher priority) |
| `header_regex` | text | Regex with named groups to extract header fields |
| `line_item_regex` | text | Regex with named groups to extract line-item fields |
| `regex_flags` | text | Flags for regex compilation (e.g., `IGNORECASE,DOTALL`) |
| `extraction_stages` | json | Ordered array of extraction operations |
| `field_map` | json | Maps regex group names → output field names |
| `execution_plan` | json | Ordered array of transform rule keys |
| `transform_rules` | json | Dict of named transform operations |
| `output_spec` | json | Required fields, validation checks, output schema |
| `sample_md5` | text | MD5 of a representative sample invoice |
| `is_active` | bool | Whether this pattern is in production |
| `created_at` | timestamp | |
| `updated_at` | timestamp | |
| `notes` | text | Free-form notes about this format |

During build, patterns are stored as JSON files in `patterns/json/` that mirror this schema exactly. The executor loads from JSON (`--source json`) or from the database (`--source db`). The JSON file IS the database row.

---

## What Raw OCR Text Is

When an invoice PDF goes through Tesseract, the output is raw text — a single string with all the text from the invoice, in reading order. No structure, no columns, no tables. Just text with newlines.

This is what the executor works with. Not the PDF. Not parsed fields from a prior step. Raw OCR text only.

The pattern is built by reading raw OCR text alongside the source PDF. The expectation is that future processing will never see the PDF — extraction, transformation, and validation all happen from the OCR text alone, successfully.

---

## Pattern Record Structure

A pattern record answers five questions:

### 1. routing_regex — How do I recognize this format?

```json
"routing_regex": "OBINSON\\s+WASTE\\s+SERVICES"
```

The executor tries each active pattern's `routing_regex` against the raw OCR, ordered by `routing_priority`. First match wins. This is how the executor selects which pattern to load.

### 2. extraction_stages — How do I pull structured fields out of the OCR?

An ordered array of regex operations that populate a shared context dict.

```json
"extraction_stages": [
  {
    "name": "header",
    "method": "search",
    "pattern": "INVOICE\\s+NO\\.?\\s+(?P<invoice_number>[A-Z]{0,3}\\d{7,10})...",
    "flags": ["IGNORECASE", "DOTALL"],
    "field_map": {"invoice_number": "invoice_number", "body": "_raw_body"}
  },
  {
    "name": "service_blocks",
    "method": "finditer",
    "source": "_raw_body",
    "pattern": "Serv\\s+#(?P<serv_num>\\d+)...",
    "field_map": {"raw_block": "_service_blocks"}
  }
]
```

- `method: search` — one match (headers)
- `method: finditer` — all matches (repeating blocks)
- Fields prefixed with `_` are internal intermediates — they feed later stages, not output
- `field_map` maps regex named groups → context field names

### 3. execution_plan — What order do I run the transforms?

```json
"execution_plan": [
  "page_header_strip",
  "weight_extraction",
  "charge_amount",
  "equipment_detection",
  "material_detection",
  "charge_normalize",
  "invoice_total"
]
```

Sequential. Order matters — weight must be extracted before charge amounts so tonnage values don't leak into the amount pool.

### 4. transform_rules — What does each transform do?

```json
"transform_rules": {
  "bill_total": {
    "type": "currency_parse",
    "strip_comma": true,
    "strip_dollar": true
  },
  "weight_extraction": {
    "type": "regex_capture",
    "pattern": "(\\d+(?:\\.\\d+)?)\\s*Tons?",
    "output_field": "weight",
    "filter_from_amounts": true
  },
  "charge_normalize": {
    "type": "charge_normalize",
    "equipment_class_map": {"FRONT_LOAD": "commercial", "OPEN_TOP": "industrial"},
    "lookup": {"Dump & Return": "Empty & Return", "Disposal": "Disposal Charge"}
  }
}
```

Each rule has a `type` that selects the handler. All other fields are config passed to that handler. Handlers read from context, transform, write back to context.

### 5. output_spec — How do I know the output is correct?

```json
"output_spec": {
  "header_fields": ["invoice_date", "account_number", "invoice_number", "bill_total"],
  "charge_fields": ["service_date", "description", "charge_total", "equipment_type", "equipment_size", "material", "charge_code", "weight"],
  "validation": {
    "required_header": ["invoice_number", "bill_total"],
    "charge_sum_check": true
  }
}
```

After all transforms complete, the executor validates against `output_spec`. Missing required fields → fail. Charge sum mismatch → fail. No silent passes.

---

## The Context Dict

Shared state that flows through extraction and transformation. Starts empty.

```
context = {}

# After header extraction:
context = {
  "invoice_date": "12/31/2025",    # raw string from OCR
  "bill_total": "$22,981.10",       # raw string from OCR
  "_raw_body": "..."                # internal intermediate
}

# After bill_total transform (currency_parse):
context = {
  "invoice_date": "12/31/2025",
  "bill_total": 22981.10,           # now a float
  "_raw_body": "..."
}
```

Handlers read named fields from context, transform them, write results back. The executor passes the full context — never individual values.

---

## The Handler Registry

Fixed set of handler types. Each is a Python function with the same signature:

```python
def handle_{type}(config: dict, context: dict) -> dict:
    # read from context
    # apply transform described by config
    # write result back to context
    return context
```

Handlers have no knowledge of which vendor they run for. All vendor-specific behavior is config in the pattern record.

| Handler Type | What It Does |
|---|---|
| `currency_parse` | Strip $, commas → float |
| `date_parse` | Parse date string → date object |
| `multi_heuristic` | Try multiple amount extraction strategies in order |
| `regex_strip` | Remove pattern from text (e.g., page headers) |
| `regex_capture` | Extract value via regex, optionally filter from amounts |
| `parent_container` | Attach orphan charges to nearest parent (bidirectional) |
| `multi_strategy` | Try multiple extraction strategies, first match wins |
| `date_split` | Split text block by date lines into chunks |
| `column_positional` | Extract amounts from columnar OCR by position |
| `line_filter` | Drop lines matching reject pattern |
| `parent_attach` | Fold matching lines into preceding item as metadata |
| `split_field` | Split one field into multiple on delimiter |
| `contract_anchor_walk` | Walk lines, anchor pattern identifies block boundaries |
| `single_line_parse` | Parse structured line into multiple fields via single regex |
| `line_classify` | Classify lines by type (CHARGE vs TAX vs METADATA) |
| `lookup_map` | Normalize values via lookup table in config |
| `charge_normalize` | Equipment-class-aware charge description normalization |

If a new vendor requires behavior these 17 types cannot express, the handler registry is extended. The extension is generic (usable by any future pattern), not vendor-specific.

---

## Iteration (Nested Loops)

Some formats have repeating blocks — WM has location sections, Robinson has service sections, each containing multiple charge lines.

```json
"iteration_blocks": "_service_blocks"
```

When set, the executor loops over `context["_service_blocks"]` and runs the `execution_plan` once per block. Formats without repeating blocks omit this field — the execution_plan runs once against the full invoice.

---

## Pattern Isolation

Each pattern record describes exactly one invoice document format.

- One pattern record = one format = one processing path
- A vendor with two layouts = two records. They share nothing except `vendor_name`.
- The executor never falls back from one pattern to another.
- If an invoice matches `routing_regex` but extraction fails, it fails — it does not try a different pattern.
- The correct response to a new format variant is a new pattern record, not a modification to an existing one.
- If you find yourself adding an `if` inside a handler for an edge case — stop. That's a new pattern record or a config change, not code.

---

## Executor Invariants

The executor:
- Has no vendor-specific code paths
- Has no hardcoded field names, patterns, or values
- Makes no decisions — all decisions are in the pattern record
- Loads patterns from JSON files or from `ip_vendor_pattern_bulk` in the database
- Produces one output format defined by `output_spec` regardless of vendor
- Fails loudly with a reason, never silently
