# Billing Modernization — Invoice Processing Pipeline

**Purpose:** End-to-end invoice processing system — PDF ingestion through OCR, deterministic pattern-based extraction, human-in-the-loop validation, charge catalog reconciliation, and service linkage.

**Database:** PostgreSQL (`wasteology_ops` schema)

---

## System Architecture

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                      BILLING MODERNIZATION PIPELINE                              │
├─────────────────────────────────────────────────────────────────────────────────┤
│                                                                                  │
│  ┌──────────────┐     ┌──────────────────┐     ┌──────────────────────────┐     │
│  │ Invoice PDFs │────►│  OCR Pipeline    │────►│  Pattern Executor        │     │
│  │ (SharePoint) │     │  (Tesseract)     │     │  (43 vendor patterns)    │     │
│  └──────────────┘     └──────────────────┘     │  JSON config-driven      │     │
│                                                 │  26+ handler types       │     │
│                                                 └────────────┬─────────────┘     │
│                                                              │                   │
│                                                              ▼                   │
│  ┌───────────────────────────────────────────────────────────────────────────┐   │
│  │  HITL Review (6-Gate UI)                                                  │   │
│  │  G1: OCR Quality  G2: Pattern Routing  G3: Charge Totals                 │   │
│  │  G4: Charge Details  G5: Service Match  G6: Export                        │   │
│  └────────────────────────────────┬──────────────────────────────────────────┘   │
│                                   │                                              │
│                                   ▼                                              │
│  ┌───────────────────────────────────────────────────────────────────────────┐   │
│  │  Charge Catalog Reconciliation  ◄── THE INTEGRATION GAP                   │   │
│  │  ip_service_catalog (ERP)  ←→  extracted charges (OCR)                    │   │
│  │  See: CHARGE_CATALOG_RECONCILIATION.md                                    │   │
│  └────────────────────────────────┬──────────────────────────────────────────┘   │
│                                   │                                              │
│                                   ▼                                              │
│  ┌───────────────────────────────────────────────────────────────────────────┐   │
│  │  Invoice Linkage                                                          │   │
│  │  3-layer resolution (GAPI → regex → manual)                               │   │
│  │  Fuzzy match: vendor + amount + date + address → billing_charges          │   │
│  │  Output: account_location_map (account → service_id)                      │   │
│  └───────────────────────────────────────────────────────────────────────────┘   │
│                                                                                  │
│  ┌───────────────────────────────────────────────────────────────────────────┐   │
│  │  Conformed Output                                                         │   │
│  │  invoice_raw + line_item_raw → ready for downstream analytics             │   │
│  └───────────────────────────────────────────────────────────────────────────┘   │
│                                                                                  │
└─────────────────────────────────────────────────────────────────────────────────┘
```

---

## Repository Structure

```
billing-modernization/
│
├── README.md                          # This file
├── SCHEMA.md                          # Full database schema (36 tables + 2 views)
├── CHARGE_CATALOG_RECONCILIATION.md   # The integration gap — start here
│
├── extraction/                        # Active extraction engine
│   ├── executor.py                    # Universal JSON pattern executor (26+ handlers)
│   ├── app.py                         # Flask HITL review UI (port 5051)
│   ├── db.py                          # PostgreSQL data access layer
│   ├── normalize_charges.py           # Charge code normalization (29 codes → canonical)
│   ├── ocr_pipeline.py                # Tesseract OCR + quality scoring
│   ├── run_ocr.py                     # Batch OCR coordinator
│   ├── ocr_validation.py              # OCR quality validation
│   ├── vendor_inventory.py            # Vendor detection from OCR text
│   ├── validate_output.py             # Cross-invoice semantic validation
│   ├── diff_tool.py                   # Regression testing (baseline vs current)
│   ├── reocr_failures.py              # Re-OCR failed invoices
│   └── output/
│       ├── charge_code_ref.csv        # 171 canonical charge codes
│       └── charge_code_aliases.json   # Non-canonical → canonical mapping
│
├── pipeline/                          # 7-step field extraction pipeline
│   ├── step_runner.py                 # Step orchestration (Steps 1-10)
│   ├── processor.py                   # 5-step pipeline (OCR → vendor → account → lookup → address)
│   ├── extraction_engine.py           # DB-driven pattern executor (4 scan types)
│   ├── field_extractor.py             # Form field extraction
│   ├── validators.py                  # Per-field validation (format, behavioral, position)
│   ├── catalog_seeder.py              # Build ip_service_catalog from ERP data
│   ├── review_resolver.py             # HITL action handlers
│   ├── gate_check.py                  # Gate advancement logic
│   ├── app.py                         # HTTP API server (Flask)
│   ├── database.py                    # PostgreSQL helpers
│   ├── loader.py                      # OCR document ingestion
│   ├── ai_suggestions.py              # AI helper (Claude API for group suggestions)
│   ├── suggestions.py                 # Human override workflow
│   ├── invoice_renderer.py            # OCR → displayable HTML
│   ├── meta_helper.py                 # Pattern testing/validation utilities
│   ├── ocr_pipeline.py                # OCR processing (Tesseract + GCS fallback)
│   └── reprocess.py                   # Reprocess subset of documents
│
├── linkage/                           # Invoice → service matching
│   ├── linkage.py                     # Invoice-to-service linkage
│   ├── enricher.py                    # Enrich invoice_registry with extracted fields
│   ├── matcher.py                     # Fuzzy match (vendor + amount + date + address)
│   ├── resolver.py                    # Aggregate → account_location_map
│   ├── address.py                     # Fuzzy address scoring
│   └── schema.py                      # Linkage table DDL
│
├── schema/                            # Database DDL
│   ├── invoice_pipeline.py            # ip_* extraction pipeline tables
│   ├── layer1_raw.py                  # invoice_raw, line_item_raw
│   ├── layer2_operational.py          # vendor, customer, services_current, billing_charges, etc.
│   └── reference_tables.py            # charge_code_ref, waste_stream_ref, container refs
│
├── docs/                              # Reference documentation
│   ├── ARCHITECTURE.md                # Design principles (infra-as-code, determinism)
│   ├── OUTPUT_SPEC.md                 # 23 canonical output columns + vendor-specific
│   ├── PATTERN_BUILD_PROCESS.md       # 7-gate pattern build process
│   └── LEARNINGS.md                   # Accumulated extraction lessons (Tesseract conventions)
│
├── database.py                        # Schema orchestrator (init, reset, atomic_rebuild)
├── config.py                          # Central config (PG_CONFIG, thresholds)
├── azure_helpers.py                   # Azure SQL connection helpers
├── account_resolver.py                # Account resolution from extracted data
├── charge_code_mapper.py              # Charge code → canonical SKU mapping
└── load_vendor_patterns.py            # Load patterns → database
```

---

## Key Design Principles

1. **Infrastructure as Code** — All vendor-specific knowledge lives in JSON pattern records. Never hardcode patterns, vendors, or field names in executor code.

2. **Pattern Isolation** — One pattern = one invoice format = one processing path. A vendor with two layouts gets two patterns. Never merge or fall back between patterns.

3. **Determinism** — No confidence intervals, no probabilistic matching, no dark failures. A field is extracted or it isn't. Every failure surfaces with a reason.

4. **OCR-Only Extraction** — The executor only sees OCR text. It never sees PDFs. Patterns must work on Tesseract output.

5. **Account-First Linkage** — Never match OCR invoice_number directly to billing_reference (truncated on grouped billing). Account number extraction is the deterministic path to service_id.

6. **Account Number Priority** — If an account number exists on an invoice, extract it. Account → service_id is deterministic. Address matching is a last resort.

---

## Critical Rules

> [!CAUTION]
> **PostgreSQL Batch Operations** — ALL writes must use `psycopg2.extras.execute_values()` or `execute_batch()` with `page_size=1000`. For datasets >10k rows, commit in batches of 5,000-10,000. Never loop single INSERT/UPDATE over large result sets.

> [!CAUTION]
> **Charge Catalog Reconciliation** — The extraction engine normalizes charge codes using a hardcoded 29-code map. The ERP service catalog uses a different vocabulary. These two vocabularies are NOT harmonized. See `CHARGE_CATALOG_RECONCILIATION.md` for the full gap analysis and integration scope.

---

## Database Schema

See `SCHEMA.md` for full column-level definitions of all 36 tables + 2 views:

| Section | Tables | Purpose |
|---------|--------|---------|
| A. Extraction Pipeline | 11 + 1 view | OCR → pattern matching → field extraction → validation → gate progression |
| B. HITL App | 7 | Run lifecycle, 6-gate review UI, pattern configs |
| C. Raw Inbound | 3 | Conformed invoice/line item data for downstream |
| D. Invoice Linkage | 3 | Match invoices → billing → services → locations |
| E. Operational Reference | 12 | vendor, customer, location, services, billing, charge codes, waste streams, containers, account resolution |

---

## Entry Points

| Task | Module | Command |
|------|--------|---------|
| Run OCR on new PDFs | `extraction/run_ocr.py` | `python run_ocr.py --input <pdf_dir> --output output/ocr_results.csv` |
| Run pattern executor | `extraction/executor.py` | `python executor.py --ocr output/ocr_results.csv` |
| Run single pattern | `extraction/executor.py` | `python executor.py --ocr output/ocr_results.csv --filter-pattern rob_invoice` |
| Start HITL review UI | `extraction/app.py` | `python app.py --port 5051` |
| Regression test | `extraction/diff_tool.py` | `python diff_tool.py --baseline <base.csv> --current <new.csv>` |
| Validate output | `extraction/validate_output.py` | `python validate_output.py --input output/vendor_extracts/<format>.csv` |
| Normalize charges | `extraction/normalize_charges.py` | `python normalize_charges.py` |

---

## Documentation Guide

| Document | Purpose | Read When |
|----------|---------|-----------|
| `SCHEMA.md` | Full database schema (36 tables) | Understanding data model |
| `CHARGE_CATALOG_RECONCILIATION.md` | The integration gap — what needs to be built | Scoping the deliverable |
| `docs/ARCHITECTURE.md` | Design principles, handler registry | Modifying or extending the executor |
| `docs/OUTPUT_SPEC.md` | 23 canonical columns + vendor-specific | Building new patterns or validating output |
| `docs/PATTERN_BUILD_PROCESS.md` | 7-gate supervised build process | Adding new vendor patterns |
| `docs/LEARNINGS.md` | Tesseract OCR conventions, multi-format handling | Debugging extraction failures |
