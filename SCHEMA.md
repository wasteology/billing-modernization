# Invoice Processing Pipeline — Database Schema

**Database:** `wasteology_dev` on `pg-wasteology.postgres.database.azure.com`
**Schema:** `wasteology_ops`
**Last Updated:** 2026-05-10

---

## Overview

The invoice processing pipeline spans three subsystems that share a single PostgreSQL schema:

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                        INVOICE PROCESSING DATA MODEL                            │
├─────────────────────────────────────────────────────────────────────────────────┤
│                                                                                 │
│  ┌──────────────────────────────────────────────────────────────────────────┐   │
│  │  A. EXTRACTION PIPELINE (ip_* tables)                                    │   │
│  │     PDF → OCR → Pattern Matching → Field Extraction → Validation         │   │
│  │     → Human Review → Gate Progression → Line Item Matching               │   │
│  │                                                                          │   │
│  │  11 tables + 1 view                                                      │   │
│  └──────────────────────────────────┬───────────────────────────────────────┘   │
│                                     │                                           │
│                                     ▼                                           │
│  ┌──────────────────────────────────────────────────────────────────────────┐   │
│  │  B. HITL APP (ip_run*, ip_invoice, ip_charge, ip_vendor_pattern_bulk)    │   │
│  │     Run lifecycle → 6-gate review UI → Export                            │   │
│  │                                                                          │   │
│  │  7 tables                                                                │   │
│  └──────────────────────────────────┬───────────────────────────────────────┘   │
│                                     │                                           │
│                                     ▼                                           │
│  ┌──────────────────────────────────────────────────────────────────────────┐   │
│  │  C. RAW INBOUND (invoice_raw, line_item_raw, ocr_document)               │   │
│  │     Conformed invoice data lands here for ops_database consumption        │   │
│  │                                                                          │   │
│  │  3 tables                                                                │   │
│  └──────────────────────────────────┬───────────────────────────────────────┘   │
│                                     │                                           │
│                                     ▼                                           │
│  ┌──────────────────────────────────────────────────────────────────────────┐   │
│  │  D. INVOICE LINKAGE (invoice_registry, invoice_service_match,            │   │
│  │     account_location_map)                                                │   │
│  │     Match invoices → billing_charges → services → locations              │   │
│  │                                                                          │   │
│  │  3 tables                                                                │   │
│  └──────────────────────────────────┬───────────────────────────────────────┘   │
│                                     │                                           │
│                                     ▼                                           │
│  ┌──────────────────────────────────────────────────────────────────────────┐   │
│  │  E. OPS_DATABASE TABLES (referenced by pipeline)                         │   │
│  │     vendor, customer, location, services_current, billing_charges,       │   │
│  │     charge_code_ref, account_number_resolution, vendor_name_mapping,     │   │
│  │     ap_report                                                            │   │
│  │  9 tables (subset relevant to invoice pipeline)                          │   │
│  └──────────────────────────────────────────────────────────────────────────┘   │
│                                                                                 │
└─────────────────────────────────────────────────────────────────────────────────┘
```

**Table Count:** 33 tables + 2 views

---

## A. Extraction Pipeline Tables (`ip_*`)

Source: `/ops_database/src/schema/invoice_pipeline.py`

These tables manage the 7-step field extraction pipeline with pattern matching, validation, human review, and gate progression.

### A1. ip_raw_document

Immutable OCR source text. One row per unique PDF (keyed by MD5 hash of content).

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `md5_hash` | TEXT | **PK** | MD5 of raw OCR text |
| `sp_created_date` | DATE | | SharePoint upload date |
| `source_file` | TEXT | | Original filename |
| `raw_ocr_text` | TEXT | | Full Tesseract OCR output |
| `sync_date` | TIMESTAMP | DEFAULT NOW() | When synced from SharePoint |
| `sync_status` | TEXT | CHECK IN ('OK','NO_TEXT','NOT_FOUND','ERROR') | Sync outcome |

---

### A2. ip_vendor_pattern

Vendor-specific regex extraction patterns. Versioned, with multi-match support for charge line extraction.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `vendor_pattern_id` | SERIAL | **PK** | |
| `vendor_name` | TEXT | NOT NULL | Vendor this pattern serves |
| `field` | TEXT | NOT NULL | Target field (detected_vendor, account_number, etc.) |
| `format_variant` | INTEGER | DEFAULT 1 | Invoice format variant |
| `pattern_type` | TEXT | CHECK IN ('PRIMARY','FALLBACK','GENERIC') | Pattern tier |
| `priority` | INTEGER | NOT NULL | Execution order within field |
| `regex_pattern` | TEXT | NOT NULL | The regex |
| `regex_flags` | TEXT | DEFAULT 'IGNORECASE' | Python re flags |
| `capture_group` | INTEGER | DEFAULT 1 | Which capture group to extract |
| `normalization` | TEXT | DEFAULT 'NONE' | Post-capture normalization |
| `scan_type` | TEXT | CHECK IN ('INLINE','FORWARD_COLUMNAR','REVERSE_COLUMNAR','WIDE_COLUMNAR') | OCR scan strategy |
| `scan_lines` | INTEGER | DEFAULT 1 | Lines to scan for columnar |
| `date_format` | TEXT | | strptime format for date fields |
| `is_no_account` | BOOLEAN | DEFAULT FALSE | Vendor has no account numbers |
| `is_active` | BOOLEAN | DEFAULT TRUE | |
| `version` | INTEGER | DEFAULT 1 | Pattern version |
| `prior_version_id` | INTEGER | FK → self | Previous version |
| `valid_from` | TIMESTAMP | DEFAULT NOW() | |
| `valid_to` | TIMESTAMP | | NULL = current |
| `deployed_by` | TEXT | | Who deployed |
| `deployed_at` | TIMESTAMP | DEFAULT NOW() | |
| `notes` | TEXT | | |
| `execution_mode` | TEXT | CHECK IN ('SINGLE','MULTI'), DEFAULT 'SINGLE' | Single value vs multi-match |
| `capture_map` | JSONB | | Named group → output field mapping |
| `pattern_tier` | TEXT | CHECK IN ('TIER_1','TIER_2','TIER_FALLBACK'), DEFAULT 'TIER_1' | |
| `activation_condition` | TEXT | | Conditional activation rule |
| `description_template` | TEXT | | Template for charge descriptions |

**Unique:** `(vendor_name, field, format_variant, priority, version)`

---

### A3. ip_vendor_profile

Statistical profile of expected values per vendor+field. Used for anomaly detection and validation.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `vendor_profile_id` | SERIAL | **PK** | |
| `vendor_name` | TEXT | NOT NULL | |
| `field` | TEXT | NOT NULL | |
| `format_variant` | INTEGER | DEFAULT 1 | |
| `detection_zone` | TEXT | | Where in OCR text the field appears |
| `co_occurrence_markers` | TEXT | | Nearby text markers |
| `layout_fingerprint` | TEXT | | OCR layout signature |
| `value_length_min` | INTEGER | | Expected min length |
| `value_length_max` | INTEGER | | Expected max length |
| `value_composition` | TEXT | | Character composition (digits, alpha, mixed) |
| `value_prefix_pattern` | TEXT | | Common prefix |
| `known_value_examples` | TEXT | | Confirmed values |
| `confirmed_invoice_count` | INTEGER | DEFAULT 0 | |
| `profile_status` | TEXT | CHECK IN ('ACTIVE','STALE','BUILDING'), DEFAULT 'ACTIVE' | |
| `created_at` | TIMESTAMP | DEFAULT NOW() | |
| `updated_at` | TIMESTAMP | DEFAULT NOW() | |

**Unique:** `(vendor_name, field, format_variant)`

---

### A4. ip_extraction_result

Every extraction attempt — successful or not. Links back to the pattern that produced it.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `extraction_result_id` | SERIAL | **PK** | |
| `md5_hash` | TEXT | NOT NULL, FK → ip_raw_document | |
| `step` | INTEGER | NOT NULL | Pipeline step (1-7) |
| `attempt` | INTEGER | DEFAULT 1 | Attempt number |
| `field` | TEXT | NOT NULL | Field extracted |
| `extracted_value` | TEXT | | The extracted value |
| `extraction_source` | TEXT | CHECK IN ('ENGINE','OVERRIDE','REPROCESS') | How value was obtained |
| `vendor_pattern_id` | INTEGER | FK → ip_vendor_pattern | Pattern that produced this |
| `extracted_at` | TIMESTAMP | DEFAULT NOW() | |

---

### A5. ip_validation_result

Validation checks run against extraction results. One row per check per document.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `validation_result_id` | SERIAL | **PK** | |
| `extraction_result_id` | INTEGER | NOT NULL, FK → ip_extraction_result | |
| `md5_hash` | TEXT | NOT NULL | |
| `step` | INTEGER | NOT NULL | |
| `check_name` | TEXT | NOT NULL | Validation check identifier |
| `check_result` | TEXT | NOT NULL, CHECK IN ('PASS','FAIL') | |
| `confidence` | TEXT | CHECK IN ('HIGH','LOW') | |
| `detail` | TEXT | | Failure detail |
| `checked_at` | TIMESTAMP | DEFAULT NOW() | |

---

### A6. ip_review_queue

Human-in-the-loop review items. Failed validations and ambiguous extractions land here.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `review_queue_id` | SERIAL | **PK** | |
| `md5_hash` | TEXT | NOT NULL, FK → ip_raw_document | |
| `step` | INTEGER | NOT NULL | |
| `fail_category` | TEXT | NOT NULL | Category of failure |
| `ai_suggestion` | TEXT | | Suggested correction |
| `suggestion_confidence` | TEXT | CHECK IN ('HIGH','MEDIUM','LOW','NONE') | |
| `suggestion_reason` | TEXT | | |
| `human_action` | TEXT | CHECK IN ('ACCEPT','SET','SKIP','EXCLUDE','REROUTE','CONFIRM_NO_ACCOUNT','MAP','ADD_TO_CATALOG','EXCLUDE_CONTAINER','ACCEPT_VARIANCE','DISPUTE','ACCEPT_NEW_CHARGE','REJECT_CHARGE') | |
| `corrected_value` | TEXT | | Human-provided value |
| `reroute_target` | TEXT | | |
| `notes` | TEXT | | |
| `status` | TEXT | DEFAULT 'OPEN', CHECK IN ('OPEN','RESOLVED','REROUTED') | |
| `opened_at` | TIMESTAMP | DEFAULT NOW() | |
| `resolved_at` | TIMESTAMP | | |
| `resolved_by` | TEXT | | |
| `pdf_link` | TEXT | | Link to source PDF |

---

### A7. ip_pipeline_event

Immutable audit log of every pipeline action per document.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `pipeline_event_id` | SERIAL | **PK** | |
| `md5_hash` | TEXT | NOT NULL, FK → ip_raw_document | |
| `step` | INTEGER | NOT NULL | |
| `event_type` | TEXT | NOT NULL, CHECK IN ('EXTRACTED','VALIDATION_PASS','VALIDATION_FAIL','QUEUED_REVIEW','ACCEPTED','CORRECTED','EXCLUDED','REROUTED','GATE_PASSED','GATE_BLOCKED','REPROCESSED','EXCLUSION_REVERSED','DISPUTE','REJECTED_CHARGE','CATALOG_UPDATED') | |
| `field` | TEXT | | Field affected |
| `value` | TEXT | | New value |
| `prior_event_id` | INTEGER | FK → self | Previous event in chain |
| `human_actor` | TEXT | | Who did it |
| `review_queue_id` | INTEGER | FK → ip_review_queue | |
| `notes` | TEXT | | |
| `event_at` | TIMESTAMP | DEFAULT NOW() | |

---

### A8. ip_gate_result

Per-document gate status. Each document must pass all 7 gates.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `gate_result_id` | SERIAL | **PK** | |
| `md5_hash` | TEXT | NOT NULL, FK → ip_raw_document | |
| `step` | INTEGER | NOT NULL | Gate number (1-7) |
| `gate_status` | TEXT | NOT NULL, CHECK IN ('PASSED','BLOCKED','EXCLUDED') | |
| `passed_at` | TIMESTAMP | | When gate was passed |
| `last_event_id` | INTEGER | FK → ip_pipeline_event | |

**Unique:** `(md5_hash, step)`

---

### A9. ip_fix_log

Tracks pattern fixes triggered by review queue failures.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `fix_log_id` | SERIAL | **PK** | |
| `created_at` | TIMESTAMP | DEFAULT NOW() | |
| `step` | INTEGER | NOT NULL | |
| `fail_category` | TEXT | NOT NULL | |
| `vendor` | TEXT | NOT NULL | |
| `md5_sample` | TEXT | | Sample document hash |
| `ocr_sample` | TEXT | | Sample OCR text |
| `fix_type` | TEXT | CHECK IN ('NEW_PATTERN','PATTERN_FIX','NO_ACCOUNT_CONFIRM') | |
| `fix_status` | TEXT | DEFAULT 'OPEN', CHECK IN ('OPEN','IN_PROGRESS','DEPLOYED','CLOSED') | |
| `vendor_pattern_id` | INTEGER | FK → ip_vendor_pattern | Resulting pattern |
| `deployed_at` | TIMESTAMP | | |
| `closed_at` | TIMESTAMP | | |
| `review_queue_id` | INTEGER | FK → ip_review_queue | |
| `notes` | TEXT | | |

---

### A10. ip_service_catalog

Known container/service configurations per account. Built from confirmed extractions.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `catalog_id` | SERIAL | **PK** | |
| `service_id` | TEXT | NOT NULL | Linked CIE service |
| `account_number` | TEXT | NOT NULL | Hauler account number |
| `vendor` | TEXT | NOT NULL | |
| `container_id` | TEXT | NOT NULL | Container identifier |
| `container_index` | INTEGER | NOT NULL | Position on invoice |
| `equipment_type` | TEXT | NOT NULL | FRONT_LOAD, OPEN_TOP, etc. |
| `equipment_size` | TEXT | | Size (yards, gallons) |
| `material` | TEXT | | Waste stream |
| `schedule` | TEXT | | Pickup schedule |
| `charge_type` | TEXT | NOT NULL | Charge classification |
| `expected_rate` | NUMERIC(12,4) | | Expected charge amount |
| `rate_uom` | TEXT | | Rate unit of measure |
| `invoice_level_charge_pct` | NUMERIC(6,4) | | % of invoice-level charges to allocate |
| `catalog_status` | TEXT | DEFAULT 'BUILDING', CHECK IN ('BUILDING','CONFIRMED','STALE') | |
| `confirmed_at` | TIMESTAMP | | |
| `confirmed_by` | TEXT | | |
| `created_at` | TIMESTAMP | DEFAULT NOW() | |
| `updated_at` | TIMESTAMP | DEFAULT NOW() | |

---

### A11. ip_invoice_line_item

Matched line items — extracted charges matched against the service catalog.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `line_item_id` | SERIAL | **PK** | |
| `md5_hash` | TEXT | NOT NULL, FK → ip_raw_document | |
| `invoice_date` | DATE | | |
| `invoice_total` | NUMERIC(12,2) | | |
| `vendor` | TEXT | | |
| `account_number` | TEXT | | |
| `container_index` | INTEGER | NOT NULL | Position on invoice |
| `equipment_type` | TEXT | | |
| `equipment_size` | TEXT | | |
| `material` | TEXT | | |
| `schedule` | TEXT | | |
| `container_id` | TEXT | | Linked to ip_service_catalog |
| `service_id` | TEXT | | Linked to services_current |
| `charge_type` | TEXT | | |
| `billed_amount` | NUMERIC(12,4) | | Amount on invoice |
| `expected_amount` | NUMERIC(12,4) | | Amount from catalog |
| `variance` | NUMERIC(12,4) | | billed - expected |
| `variance_pct` | NUMERIC(8,4) | | Variance as percentage |
| `status` | TEXT | NOT NULL, CHECK IN ('MATCH','RATE_VARIANCE','UNEXPECTED_CHARGE','MISSING_CHARGE','UNMATCHED_CONTAINER','INVOICE_LEVEL_VARIANCE','PENDING','EXCLUDED') | |
| `created_at` | TIMESTAMP | DEFAULT NOW() | |

---

### A12. ip_staging_invoice (VIEW)

Flattened view joining extraction results across all 7 gates. Used for pipeline status dashboards.

```sql
CREATE OR REPLACE VIEW ip_staging_invoice AS
SELECT
    r.md5_hash,
    r.sp_created_date,
    r.source_file,
    e_vendor.extracted_value    AS detected_vendor,
    e_account.extracted_value   AS hauler_account_number,
    e_invoice.extracted_value   AS hauler_invoice_number,
    e_date.extracted_value      AS invoice_date,
    e_amount.extracted_value    AS bill_total,
    g1.gate_status              AS step1_status,
    g2.gate_status              AS step2_status,
    g3.gate_status              AS step3_status,
    g4.gate_status              AS step4_status,
    g5.gate_status              AS step5_status,
    g6.gate_status              AS step6_status,
    g7.gate_status              AS step7_status
FROM ip_raw_document r
JOIN ip_gate_result g1 ON r.md5_hash = g1.md5_hash AND g1.step = 1
    AND g1.gate_status IN ('PASSED', 'EXCLUDED')
LEFT JOIN ip_gate_result g2-g7 ...
LEFT JOIN ip_extraction_result e_vendor/e_account/e_invoice/e_date/e_amount ...
```

---

## B. HITL App Tables

Source: `/ng-report/invoices/db.py` (queries), `/invoice-poc/` (app layer)

These tables support the 6-gate review UI (Flask app on port 5051). They are consumed by `db.py` but defined at the database level.

### B1. ip_run

Run lifecycle management. Each run processes a batch of invoices through all gates.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `run_id` | SERIAL | **PK** | |
| `created_at` | TIMESTAMP | | Run creation time |
| `doc_count` | INTEGER | | Number of documents in run |
| `current_gate` | INTEGER | | Current gate (1-6) |
| `status` | TEXT | | Run status (e.g. 'active', 'pushed') |

---

### B2. ip_run_doc

Links documents to runs. Tracks per-document exclusion and gate resolution state.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `run_doc_id` | SERIAL | **PK** | |
| `run_id` | INTEGER | FK → ip_run | |
| `md5_hash` | TEXT | FK → ip_raw_document | |
| `excluded` | BOOLEAN | | Document excluded from run |
| `gate1_resolved` | BOOLEAN | | Gate 1 exceptions resolved |
| `gate2_resolved` | BOOLEAN | | Gate 2 exceptions resolved |
| `gate3_resolved` | BOOLEAN | | Gate 3 exceptions resolved |
| `gate4_resolved` | BOOLEAN | | Gate 4 exceptions resolved |
| `gate5_resolved` | BOOLEAN | | Gate 5 exceptions resolved |

---

### B3. ip_invoice

Invoice header data extracted by the pattern executor.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `md5_hash` | TEXT | **PK**, FK → ip_raw_document | |
| `vendor_name` | TEXT | | Detected vendor |
| `invoice_number` | TEXT | | |
| `invoice_date` | DATE | | |
| `account_number` | TEXT | | Hauler account number |
| `bill_total` | NUMERIC | | Invoice total from OCR |
| `charge_sum` | NUMERIC | | Sum of extracted charges |
| `num_charges` | INTEGER | | Count of extracted charges |
| `valid` | BOOLEAN | | charge_sum = bill_total |
| `diff` | NUMERIC | | charge_sum - bill_total |
| `status` | TEXT | | VALID, DIFF, UNDER_CAPTURE, NO_PATTERN |
| `pattern_id` | INTEGER | FK → ip_vendor_pattern_bulk | Pattern that extracted this |

---

### B4. ip_charge

Individual charge line items extracted from invoices.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `md5_hash` | TEXT | FK → ip_raw_document | |
| `charge_idx` | INTEGER | | Line item position |
| `service_date` | DATE | | |
| `description` | TEXT | | Charge description |
| `charge_type` | TEXT | | Charge classification |
| `charge_total` | NUMERIC | | Line item amount |
| `equipment_type` | TEXT | | FRONT_LOAD, OPEN_TOP, etc. |
| `equipment_size` | TEXT | | Container size |
| `material` | TEXT | | Waste stream |
| `schedule` | TEXT | | Pickup schedule |
| `charge_code` | TEXT | | Canonical charge code |
| `weight` | NUMERIC | | Weight (tons) |
| `weight_unit` | TEXT | | Weight UOM |
| `flag` | TEXT | | Validation flags |

---

### B5. ip_vendor_pattern_bulk

JSON pattern records for the deterministic executor. One row per vendor invoice format.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `pattern_id` | SERIAL | **PK** | |
| `bulk_pattern_id` | SERIAL | | Legacy ID |
| `vendor_name` | TEXT | | |
| `format_label` | TEXT | | Human-readable format name |
| `routing_regex` | TEXT | | Regex to match this format in OCR |
| `routing_priority` | INTEGER | DEFAULT 1 | Priority when multiple patterns match |
| `extraction_stages` | JSONB | | Field extraction config |
| `execution_plan` | JSONB | | Transform execution order |
| `transform_rules` | JSONB | | Handler configurations |
| `charge_pipeline` | JSONB | | Charge line extraction config |
| `output_spec` | JSONB | | Required fields + validation |

---

### B6. ip_gate_event

Audit log of HITL actions (accept, queue/exclude) at each gate.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `run_id` | INTEGER | FK → ip_run | |
| `md5_hash` | TEXT | FK → ip_raw_document | |
| `gate` | INTEGER | | Gate number |
| `action` | TEXT | | Action taken (accept, queue) |
| `issue` | TEXT | | Issue type resolved |

---

### B7. ip_validation_result (HITL variant)

Validation findings used by the HITL app (gates 3-4). Shares name with A5 but has additional HITL columns.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `validation_id` | SERIAL | **PK** | |
| `run_id` | INTEGER | FK → ip_run | |
| `md5_hash` | TEXT | FK → ip_raw_document | |
| `check_name` | TEXT | | CHARGE_DIFF, UNDER_CAPTURE, MISSING_BILL_TOTAL, MISSING_EQUIPMENT_TYPE, etc. |
| `severity` | TEXT | | error, warning, info |
| `detail` | TEXT | | Human-readable detail |
| `variance_pct` | NUMERIC | | Variance percentage (G3 checks) |
| `resolved` | BOOLEAN | | Whether resolved by HITL |
| `resolved_action` | TEXT | | accept or queue |
| `resolved_at` | TIMESTAMP | | |

---

## C. Raw Inbound Tables

Source: `/ops_database/MARS/reference_files/schema/ops_database.sql`

Conformed invoice data from the extraction pipeline, ready for ops_database analytical consumption.

### C1. ocr_document

Raw OCR text archive. Mirrors ip_raw_document for ops_database consumers.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `md5_hash` | TEXT | **PK** | MD5 of OCR text |
| `raw_text` | TEXT | NOT NULL | Full OCR output |
| `sp_created_date` | DATE | | SharePoint upload date |

---

### C2. invoice_raw

Conformed invoice headers after extraction pipeline completes.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `invoice_raw_id` | SERIAL | **PK** | |
| `md5_hash` | TEXT | UNIQUE | FK join key to OCR |
| `vendor_id` | INTEGER | FK → vendor | Resolved vendor |
| `hauler_account_number` | TEXT | | |
| `hauler_invoice_number` | TEXT | | |
| `bill_date` | DATE | | |
| `service_month` | INTEGER | | |
| `service_year` | INTEGER | | |
| `raw_total` | DOUBLE PRECISION | | Invoice total |
| `document_path` | TEXT | | Source file path |
| `ocr_confidence` | DOUBLE PRECISION | | OCR quality score |
| `processing_status` | TEXT | CHECK IN ('received','ocr_complete','interpreted','conformed','exception') | Pipeline stage |
| `received_datetime` | TIMESTAMP | | |
| `export_datetime` | TIMESTAMP | | |

---

### C3. line_item_raw

Conformed charge line items from extraction pipeline.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `line_item_raw_id` | SERIAL | **PK** | |
| `invoice_raw_id` | INTEGER | NOT NULL, FK → invoice_raw | |
| `line_number` | INTEGER | | Position |
| `raw_charge_description` | TEXT | | |
| `raw_waste_stream` | TEXT | | |
| `raw_container_detail` | TEXT | | |
| `raw_quantity` | DOUBLE PRECISION | | |
| `raw_unit_price` | DOUBLE PRECISION | | |
| `raw_amount` | DOUBLE PRECISION | | |
| `raw_weight` | DOUBLE PRECISION | | |
| `raw_weight_uom` | TEXT | | |
| `ocr_confidence` | DOUBLE PRECISION | | Per-field OCR confidence |

---

## D. Invoice Linkage Tables

Source: `/ops_database/src/invoice_linkage/schema.py`

Match invoice PDFs to billing locations using vendor + address + amount + date. Three-layer override model (GAPI → regex → manual).

### D1. invoice_registry

Master registry of all invoices with 3-layer field resolution.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `invoice_md5` | TEXT | **PK** | MD5 of invoice |
| | | | **--- Doc AI baseline (GAPI) ---** |
| `gapi_vendor_name` | TEXT | | Google API vendor detection |
| `gapi_service_address` | TEXT | | |
| `gapi_invoice_date` | DATE | | |
| `gapi_invoice_amount` | DOUBLE PRECISION | | |
| `gapi_account_number` | TEXT | | |
| `gapi_invoice_number` | TEXT | | |
| `gapi_counterparty` | TEXT | | |
| `gapi_site_state` | TEXT | | |
| `gapi_status` | TEXT | | |
| | | | **--- Regex overrides (parsing_engines) ---** |
| `regex_vendor_name` | TEXT | | |
| `regex_service_address` | TEXT | | |
| `regex_service_city` | TEXT | | |
| `regex_service_state` | TEXT | | |
| `regex_service_postal` | TEXT | | |
| `regex_invoice_date` | DATE | | |
| `regex_invoice_amount` | DOUBLE PRECISION | | |
| `regex_account_number` | TEXT | | |
| `regex_invoice_number` | TEXT | | |
| | | | **--- Manual overrides (human corrections) ---** |
| `manual_vendor_name` | TEXT | | |
| `manual_service_address` | TEXT | | |
| `manual_service_city` | TEXT | | |
| `manual_service_state` | TEXT | | |
| `manual_service_postal` | TEXT | | |
| `manual_invoice_date` | DATE | | |
| `manual_invoice_amount` | DOUBLE PRECISION | | |
| `manual_account_number` | TEXT | | |
| `manual_invoice_number` | TEXT | | |
| | | | **--- Resolved best values ---** |
| `resolved_vendor_name` | TEXT | | COALESCE(manual, regex, gapi) |
| `resolved_vendor_id` | INTEGER | FK → vendor | |
| `resolved_address` | TEXT | | |
| `resolved_city` | TEXT | | |
| `resolved_state` | TEXT | | |
| `resolved_postal_code` | TEXT | | |
| `resolved_invoice_date` | DATE | | |
| `resolved_invoice_amount` | DOUBLE PRECISION | | |
| `resolved_account_number` | TEXT | | |
| `resolved_invoice_number` | TEXT | | |
| | | | **--- Status tracking ---** |
| `sp_created_date` | DATE | | SharePoint upload date |
| `enrichment_status` | TEXT | CHECK IN ('pending','gapi_only','enriched','manual_review') | |
| `match_status` | TEXT | CHECK IN ('unmatched','matched','ambiguous','excluded') | |
| `match_location_id` | INTEGER | FK → location | Matched location |
| `match_confidence` | TEXT | CHECK IN ('high','medium','low') | |
| `created_at` | TIMESTAMP | DEFAULT NOW() | |
| `updated_at` | TIMESTAMP | DEFAULT NOW() | |

**Resolution Priority:** `COALESCE(manual_*, regex_*, gapi_*)`

---

### D2. invoice_service_match

Links invoices to billing_charges and services via fuzzy matching.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `match_id` | SERIAL | **PK** | |
| `invoice_md5` | TEXT | NOT NULL, FK → invoice_registry | |
| `billing_charge_id` | INTEGER | NOT NULL, FK → billing_charges | |
| `service_id` | TEXT | NOT NULL, FK → services_current | |
| `location_id` | INTEGER | FK → location | |
| `vendor_match` | BOOLEAN | NOT NULL | Vendor names match |
| `address_match_score` | DOUBLE PRECISION | | Weighted address similarity (threshold: 0.7) |
| `date_match` | BOOLEAN | NOT NULL | Invoice dates align (±1 month) |
| `amount_residual` | DOUBLE PRECISION | | Amount difference |
| `match_method` | TEXT | | Algorithm used |
| `match_confidence` | TEXT | CHECK IN ('high','medium','low') | |
| `created_at` | TIMESTAMP | DEFAULT NOW() | |

---

### D3. account_location_map

Aggregated output: maps hauler account numbers to locations. Final linkage product.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `map_id` | SERIAL | **PK** | |
| `vendor_id` | INTEGER | NOT NULL, FK → vendor | |
| `hauler_account_number` | TEXT | NOT NULL | |
| `location_id` | INTEGER | NOT NULL, FK → location | |
| `customer_id` | INTEGER | FK → customer | |
| `invoice_count` | INTEGER | | Invoices supporting this mapping |
| `first_seen_date` | DATE | | |
| `last_seen_date` | DATE | | |
| `total_invoiced_amount` | DOUBLE PRECISION | | |
| `confidence` | TEXT | CHECK IN ('high','medium','low','manual') | |
| `evidence_summary` | TEXT | | |
| `is_active` | BOOLEAN | DEFAULT TRUE | |
| `is_manual_override` | BOOLEAN | DEFAULT FALSE | |
| `created_at` | TIMESTAMP | DEFAULT NOW() | |
| `updated_at` | TIMESTAMP | DEFAULT NOW() | |

**Unique:** `(vendor_id, hauler_account_number, location_id)`

---

## E. Referenced ops_database Tables

Source: `/ops_database/MARS/reference_files/schema/ops_database.sql`

These tables are not part of the invoice pipeline itself but are referenced by FK or join from pipeline tables.

### E1. vendor

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `vendor_id` | SERIAL | **PK** | |
| `vendor_name` | TEXT | UNIQUE INDEX | Canonical vendor name |
| `hauler_account_number` | TEXT | UNIQUE | Legacy — use account_number_resolution |
| `is_active` | BOOLEAN | | |
| `created_date` | DATE | | |

**Referenced by:** invoice_raw, invoice_registry, invoice_service_match, account_location_map, billing_charges, vendor_contract_terms, account_number_resolution, waste_stream_mapping, charge_code_mapping, vendor_name_mapping

---

### E2. customer

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `customer_id` | SERIAL | **PK** | |
| `account_name` | TEXT | UNIQUE INDEX | Dynamics CRM account name |
| `erp_account_id` | TEXT | | ERP identifier |
| `is_active` | BOOLEAN | | |
| `created_date` | DATE | | |
| `notes` | TEXT | | |

**Referenced by:** location, service_chain, billing_charges, customer_contract_terms, account_location_map, account_number_resolution

---

### E3. location

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `location_id` | SERIAL | **PK** | |
| `customer_id` | INTEGER | FK → customer | |
| `location_name` | TEXT | | |
| `site_reference` | TEXT | | |
| `address` | TEXT | | Street address |
| `city` | TEXT | | |
| `region` | TEXT | | State/region |
| `postal_code` | TEXT | | |
| `is_active` | BOOLEAN | | |
| `created_date` | DATE | | |

**Unique:** `(customer_id, location_name)` WHERE location_name IS NOT NULL

**Referenced by:** service_chain, container, services_current, billing_charges, invoice_registry, invoice_service_match, account_location_map, account_number_resolution

---

### E4. services_current

Active service contracts with 5-tier charge structure.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `service_id` | TEXT | **PK** | CIE trade service ID |
| `customer_id` | INTEGER | FK → customer | |
| `location_id` | INTEGER | FK → location | |
| `vendor_id` | INTEGER | FK → vendor | |
| `chain_id` | INTEGER | FK → service_chain | |
| `container_id` | INTEGER | FK → container | |
| `vendor_contract_id` | INTEGER | | |
| `waste_stream_id` | INTEGER | FK → waste_stream_ref | |
| `container_size_yards` | DOUBLE PRECISION | | |
| `container_type_code` | TEXT | | |
| `container_ownership` | TEXT | | |
| `equipment_number_raw` | TEXT | | |
| `equipment_type` | TEXT | | |
| `schedule` | TEXT | | |
| `times_a_week` | DOUBLE PRECISION | | |
| `pickups_per_month` | DOUBLE PRECISION | | |
| `is_on_call` | BOOLEAN | | |
| `number_of_pickups` | INTEGER | | |
| `charge_type_1..5` | TEXT | | 5-tier charge types |
| `cost_1..5` | DOUBLE PRECISION | | 5-tier costs |
| `charge_1..5` | DOUBLE PRECISION | | 5-tier charges |
| `cost_1..5_uom` | TEXT | | Cost UOMs |
| `charge_1..5_uom` | TEXT | | Charge UOMs |
| `schedule_type_1` | TEXT | | |
| `start_date` | DATE | | |
| `end_date` | DATE | | |
| `is_active` | BOOLEAN | | |
| `monthly_yards` | DOUBLE PRECISION | | |
| `profit_structure` | TEXT | | |

**Referenced by:** service_charge_tier, service_chain_membership, billing_charges, invoice_service_match, account_number_resolution, ip_service_catalog, ip_invoice_line_item

---

### E5. billing_charges

How Wasteology billed customers. Primary transactional table.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `billing_charge_id` | SERIAL | **PK** | |
| `service_id` | TEXT | NOT NULL, FK → services_current | |
| `chain_id` | INTEGER | FK → service_chain | |
| `invoice_id` | TEXT | | CIE invoice identifier |
| `group_invoice_id` | TEXT | | Grouped invoice ID |
| `billing_reference` | TEXT | | Invoice reference (may be truncated) |
| `invoice_date` | DATE | | |
| `transaction_date` | DATE | | |
| `transaction_month` | INTEGER | | |
| `transaction_year` | INTEGER | | |
| `account_name` | TEXT | | |
| `location_name` | TEXT | | |
| `vendor_name` | TEXT | | |
| `charge_description` | TEXT | | |
| `service_type` | TEXT | | |
| `equipment_type` | TEXT | | |
| `equipment_number` | TEXT | | |
| `material` | TEXT | | |
| `price` | DOUBLE PRECISION | | |
| `cost` | DOUBLE PRECISION | | |
| `charge` | DOUBLE PRECISION | | |
| `sales` | DOUBLE PRECISION | | |
| `margin` | DOUBLE PRECISION | | |
| `weight` | DOUBLE PRECISION | | |
| `charge_code_id` | INTEGER | FK → charge_code_ref | |

> [!NOTE]
> `billing_reference` is TRUNCATED on grouped billing. Never match directly
> against OCR invoice numbers. Use voucher-first linkage flow.

**Referenced by:** invoice_service_match

---

### E6. charge_code_ref

171 canonical charge codes (18 tier-1, 153 tier-2).

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `charge_code_id` | SERIAL | **PK** | |
| `charge_code` | TEXT | NOT NULL, UNIQUE | Canonical code name |
| `charge_code_name` | TEXT | | Display name |
| `classification` | TEXT | CHECK IN (18 values) | recurring, demand, variable, etc. |
| `second_attribute` | TEXT | | |
| `is_active` | BOOLEAN | DEFAULT TRUE | |

---

### E7. account_number_resolution

Maps hauler account numbers to services/locations. Multiple confidence levels.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `resolution_id` | SERIAL | **PK** | |
| `vendor_id` | INTEGER | FK → vendor | |
| `hauler_account_number` | TEXT | | |
| `customer_id` | INTEGER | FK → customer | |
| `location_id` | INTEGER | FK → location | |
| `chain_id` | INTEGER | FK → service_chain | |
| `service_id` | TEXT | FK → services_current | |
| `match_confidence` | TEXT | CHECK IN ('high','medium','low','manual') | |
| `match_method` | TEXT | | |
| `first_verified_date` | DATE | | |
| `last_verified_date` | DATE | | |
| `verification_count` | INTEGER | | |
| `is_active` | BOOLEAN | | |

**Unique:** `(vendor_id, hauler_account_number, location_id, service_id)`

---

### E8. vendor_name_mapping

Maps raw vendor name variants to canonical vendor_id.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `mapping_id` | SERIAL | **PK** | |
| `raw_vendor_name` | TEXT | | |
| `vendor_id` | INTEGER | FK → vendor | |
| `source` | TEXT | | |
| `created_date` | DATE | | |

---

### E9. ap_report

Accounts payable payment records. Used for voucher-first linkage.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `ap_record_id` | SERIAL | **PK** | |
| `vendor_name` | TEXT | | |
| `hauler_account_number` | TEXT | | |
| `invoice_date` | DATE | | |
| `invoice_total` | DOUBLE PRECISION | | |
| `payment_date` | DATE | | |
| `payment_amount` | DOUBLE PRECISION | | |
| `check_number` | TEXT | | |
| `import_datetime` | TIMESTAMP | | |

---

## Entity Relationship Diagram

```
                                 ┌─────────────────┐
                                 │    customer      │
                                 │  (customer_id)   │
                                 └───────┬──────────┘
                                         │ 1
                          ┌──────────────┼──────────────┐
                          │              │              │
                          ▼ N            ▼ N            ▼ N
                   ┌────────────┐  ┌──────────┐  ┌──────────────────┐
                   │  location  │  │ service_ │  │ customer_        │
                   │(location_id│  │  chain   │  │ contract_terms   │
                   └─────┬──────┘  └────┬─────┘  └──────────────────┘
                         │ 1            │ 1
              ┌──────────┼─────┐        │
              │          │     │        │
              ▼ N        │     ▼ N      │
        ┌───────────┐    │  ┌────────┐  │
        │ container │    │  │services│  │
        │           │    │  │_current│◄─┘
        └───────────┘    │  └───┬────┘
                         │      │ 1
                         │      │
                         │      ▼ N
                         │  ┌────────────────┐      ┌──────────┐
                         │  │billing_charges │◄─────│ vendor   │
                         │  │                │      │(vendor_id│
                         │  └───────┬────────┘      └────┬─────┘
                         │          │                    │ 1
                         │          │                    │
                         │          │              ┌─────┼──────────┐
                         │          │              │     │          │
                         │          │              ▼ N   ▼ N        ▼ N
                         │          │         ┌────────┐ ┌────────┐ ┌────────────────┐
                         │          │         │vendor_ │ │vendor_ │ │account_number_ │
                         │          │         │name_   │ │contract│ │resolution      │
                         │          │         │mapping │ │_terms  │ └────────────────┘
                         │          │         └────────┘ └────────┘
                         │          │
     INVOICE PIPELINE    │          │
     ═══════════════     │          │
                         │          │
  ┌──────────────────┐   │          │
  │ ip_raw_document  │───┼──────────┼──────────────────────────────┐
  │   (md5_hash)     │   │          │                              │
  └──────┬───────────┘   │          │                              │
         │ 1             │          │                              │
         │               │          │                              │
    ┌────┼────┐          │          │                         ┌────┴────────────┐
    │    │    │          │          │                         │invoice_registry │
    │    │    │          │          │                         │ (invoice_md5)   │
    ▼N   ▼N   ▼N         │          │                         └──────┬──────────┘
┌──────┐┌───────┐┌─────┐│          │                                │ 1
│ip_   ││ip_    ││ip_  ││          │                                │
│extrac││review ││pipe-││          │                                ▼ N
│tion_ ││_queue ││line_││          │                         ┌──────────────────┐
│result││       ││event││          │                         │invoice_service_  │
└──┬───┘└───────┘└─────┘│          │                         │match             │──► billing_charges
   │                    │          │                         └──────────────────┘
   ▼ N                  │          │                                │
┌──────────────┐        │          │                                ▼
│ip_validation_│        │          │                         ┌──────────────────┐
│result        │        │          │                         │account_location_ │
└──────────────┘        │          │                         │map               │
                        │          │                         └──────────────────┘
   ┌────────────┐       │          │
   │ ip_run     │       │          │
   │ (run_id)   │       │          │
   └────┬───────┘       │          │
        │ 1             │          │
        ▼ N             │          │
   ┌────────────┐       │          │
   │ ip_run_doc │───────┘          │
   │            │──────────────────┘
   └────────────┘
        │
        │ joins to
        ▼
   ┌────────────┐     ┌──────────────────────┐
   │ ip_invoice │     │ ip_vendor_pattern_    │
   │            │────►│ bulk                  │
   └────────────┘     └──────────────────────┘
        │
        ▼ N
   ┌────────────┐
   │ ip_charge  │
   └────────────┘
```

---

## Pipeline Data Flow

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                        END-TO-END INVOICE FLOW                              │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  1. PDF arrives on SharePoint                                               │
│     └──► Synced to ip_raw_document (md5_hash, raw_ocr_text)               │
│                                                                             │
│  2. Extraction Pipeline (7 steps)                                           │
│     ├── Step 1: Vendor Detection    ──► ip_extraction_result               │
│     ├── Step 2: Account Number      ──► ip_extraction_result               │
│     ├── Step 3: Invoice Number      ──► ip_extraction_result               │
│     ├── Step 4: Site Matching       ──► ip_extraction_result               │
│     ├── Step 5: Date Extraction     ──► ip_extraction_result               │
│     ├── Step 6: Line Items          ──► ip_extraction_result               │
│     └── Step 7: Service Matching    ──► ip_invoice_line_item               │
│     Each step: validate ──► ip_validation_result                           │
│                fail     ──► ip_review_queue                                │
│                resolve  ──► ip_pipeline_event                              │
│                pass     ──► ip_gate_result                                 │
│                                                                             │
│  3. HITL App (6-gate review)                                               │
│     ├── Run batching      ──► ip_run + ip_run_doc                          │
│     ├── Pattern execution ──► ip_invoice + ip_charge                       │
│     ├── Pattern configs   ──► ip_vendor_pattern_bulk                       │
│     ├── Validation        ──► ip_validation_result (HITL variant)          │
│     ├── HITL actions      ──► ip_gate_event                                │
│     └── Export            ──► CSV download                                 │
│                                                                             │
│  4. Conformation to ops_database                                           │
│     ├── ip_invoice ──► invoice_raw (with resolved vendor_id)               │
│     └── ip_charge  ──► line_item_raw                                       │
│                                                                             │
│  5. Invoice Linkage                                                        │
│     ├── GAPI + regex + manual ──► invoice_registry                         │
│     ├── Fuzzy match (vendor + amount + date + address)                     │
│     │   ──► invoice_service_match                                          │
│     └── Aggregate ──► account_location_map                                 │
│                                                                             │
│  6. Downstream Analytics                                                   │
│     ├── billing_charges (matched to services_current)                      │
│     ├── chain_monthly (aggregated by service chain)                        │
│     ├── margin_tracking + margin_leak_register                             │
│     └── price_increase_events                                              │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Table Summary

| # | Table | Section | PK | Row Count | Purpose |
|---|-------|---------|------|-----------|---------|
| 1 | ip_raw_document | A | md5_hash | — | Immutable OCR source |
| 2 | ip_vendor_pattern | A | vendor_pattern_id | — | Regex extraction patterns |
| 3 | ip_vendor_profile | A | vendor_profile_id | — | Field value profiles |
| 4 | ip_extraction_result | A | extraction_result_id | — | Every extraction attempt |
| 5 | ip_validation_result | A | validation_result_id | — | Validation check results |
| 6 | ip_review_queue | A | review_queue_id | — | HITL review items |
| 7 | ip_pipeline_event | A | pipeline_event_id | — | Immutable audit log |
| 8 | ip_gate_result | A | gate_result_id | — | Per-doc gate status |
| 9 | ip_fix_log | A | fix_log_id | — | Pattern fix tracking |
| 10 | ip_service_catalog | A | catalog_id | — | Known container configs |
| 11 | ip_invoice_line_item | A | line_item_id | — | Matched line items |
| 12 | ip_staging_invoice | A | (view) | — | Flattened pipeline status |
| 13 | ip_run | B | run_id | — | Run lifecycle |
| 14 | ip_run_doc | B | run_doc_id | — | Document-to-run membership |
| 15 | ip_invoice | B | md5_hash | — | Extracted invoice headers |
| 16 | ip_charge | B | (md5_hash, charge_idx) | — | Extracted charge lines |
| 17 | ip_vendor_pattern_bulk | B | pattern_id | 37+ | JSON pattern configs |
| 18 | ip_gate_event | B | (composite) | — | HITL action log |
| 19 | ip_validation_result (HITL) | B | validation_id | — | Gate 3-4 validation |
| 20 | ocr_document | C | md5_hash | — | OCR text archive |
| 21 | invoice_raw | C | invoice_raw_id | — | Conformed invoice headers |
| 22 | line_item_raw | C | line_item_raw_id | — | Conformed line items |
| 23 | invoice_registry | D | invoice_md5 | — | 3-layer invoice registry |
| 24 | invoice_service_match | D | match_id | — | Invoice → service links |
| 25 | account_location_map | D | map_id | — | Account → location output |
| 26 | vendor | E | vendor_id | 39+ | Canonical vendors |
| 27 | customer | E | customer_id | 2,097 | Customer accounts |
| 28 | location | E | location_id | — | Service locations |
| 29 | services_current | E | service_id | — | Active service contracts |
| 30 | billing_charges | E | billing_charge_id | — | CIE billing transactions |
| 31 | charge_code_ref | E | charge_code_id | 171 | Canonical charge codes |
| 32 | account_number_resolution | E | resolution_id | — | Account → service mapping |
| 33 | vendor_name_mapping | E | mapping_id | — | Vendor name aliases |
| 34 | ap_report | E | ap_record_id | — | AP payment records |
