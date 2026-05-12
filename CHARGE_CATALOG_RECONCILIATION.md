# Charge Catalog Reconciliation — Integration Gap

**Status:** Not wired
**Priority:** This is the primary integration deliverable
**Last Updated:** 2026-05-12

---

## The Problem

The invoice processing pipeline has two independent charge code vocabularies that are not harmonized:

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                       THE VOCABULARY GAP                                     │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  EXTRACTION SIDE                    ERP SIDE                                │
│  (extraction / executor.py)          (pipeline / catalog_seeder.py)          │
│                                                                              │
│  ┌──────────────────────┐           ┌──────────────────────┐                │
│  │ normalize_charges.py │           │ ip_service_catalog   │                │
│  │                      │           │                      │                │
│  │ 29-code hardcoded    │     ≠     │ charge_type from     │                │
│  │ CHARGE_CODE_MAP      │           │ service_charge_tier  │                │
│  │                      │           │ (ERP source)         │                │
│  │ "Monthly Service     │           │ "Monthly Service"    │                │
│  │  Commercial"         │           │ or "RENTAL_COMM"     │                │
│  │                      │           │ or different spelling│                │
│  └──────────┬───────────┘           └──────────┬───────────┘                │
│             │                                  │                             │
│             │          NO MAPPING               │                             │
│             │          LAYER EXISTS              │                             │
│             └──────────── ✕ ───────────────────┘                             │
│                                                                              │
│  Result: Step 9 (Catalog Match) fails on charge_type mismatch               │
│          even when equipment + size + material match correctly               │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Current State

### What the Extraction Engine Produces

`extraction/normalize_charges.py` maps OCR-extracted charge descriptions to a **hardcoded 29-code vocabulary**:

| Extraction Code | Maps To |
|----------------|---------|
| Compactor Installation Dry Run | Compactor Installation |
| Contaminated Load | Contaminated Load |
| Delivery Commercial | Delivery Commercial |
| Delivery Industrial | Delivery Industrial |
| Disposal / Disposal Charge | Disposal Charge |
| Empty & Return | Empty & Return |
| Environmental Surcharge | Environmental Surcharge |
| Extra Pick Up | Extra Pick Up |
| FUEL SURCHARGE | Fuel Surcharge Commercial |
| Final Pick Up | Final Pick Up |
| Franchise Fee Commercial | Franchise Fee Commercial |
| Inactivty Fee | Inactivity Fee |
| Local Surcharge Commercial | Local Surcharges/Fees Commercial |
| Lock Bar | Lock Bar |
| Metal Rebate | Recycling Rebate Scrap Metal |
| Miscellaneous | Miscellaneous |
| Monthly Rental Commercial | Monthly Rental Commerical |
| Monthly Rental Industrial | Monthly Rental Industrial |
| Monthly Service Commercial | Monthly Service Commercial |
| Monthly Service Industrial | Monthly Service Industrial |
| Overage | Overage |
| Recycling Offset | Recycling Service Material |
| Recycling Rebate | Recycling Rebate |
| Relocate Commercial | Relocate Commercial |
| Relocate Industrial | Relocate Industrial |
| Sales Tax / Tax Commercial | Tax Commercial |
| Trip Charge | Trip Charge |
| Vendor Late Fees | Vendor Late Fees |

Additionally, `engines/parsing/charge_code_normalization/` has a **separate 155-code engine** with 12 vendor-specific normalizers and 25+ generic rules. This engine is used by the extraction pipeline's `ip_charge.charge_code` column but is **not connected** to the catalog reconciliation.

### What the ERP Service Catalog Contains

`pipeline/catalog_seeder.py` builds `ip_service_catalog` by joining:

```
account_number_resolution → services_current → service_charge_tier
```

Each catalog row stores:
- `service_id`, `account_number`, `vendor`
- `container_id`, `container_index`
- `equipment_type`, `equipment_size`, `material`, `schedule`
- **`charge_type`** ← from `service_charge_tier` (ERP vocabulary)
- `expected_rate` ← charge amount from ERP
- `rate_uom`

The `charge_type` values come from the ERP's 5-tier charge structure on `services_current` (charge_type_1 through charge_type_5), normalized into `service_charge_tier` rows by `chain_builder.py`.

### The Matching Logic (Step 9)

`pipeline/step_runner.py` Step 9 (Catalog Match) compares extracted line items against the catalog:

1. **Exact match**: `(equipment_type, equipment_size, material)` from invoice line item vs catalog entry
2. **Fuzzy fallback**: If no exact match, try `(equipment_type, equipment_size)` only — returns match only if exactly ONE catalog entry matches
3. **If matched**: Sets `container_id`, `service_id`, `expected_amount` on the line item
4. **If unmatched**: Routes to review queue as `UNMATCHED_CONTAINER`

### The Variance Detection (Step 10)

Step 10 compares matched line items against expected catalog rates:

| Status | Meaning |
|--------|---------|
| `MATCH` | billed_amount = expected_amount |
| `RATE_VARIANCE` | billed_amount != expected_amount (outside tolerance) |
| `UNEXPECTED_CHARGE` | Invoice has charge, catalog doesn't |
| `MISSING_CHARGE` | Catalog has charge, invoice doesn't |

---

## The Three Gaps

### Gap 1: Charge Code Vocabulary Mismatch (PRIMARY)

The extraction engine's 29-code `CHARGE_CODE_MAP` and the ERP's `charge_type` values are **different vocabularies**. When Step 9 tries to match charge lines against the catalog, the `charge_type` field may not match because:

- OCR extracted `"Monthly Rental Commercial"` (from normalize_charges.py)
- ERP catalog has `"Monthly Rental"` or `"RENTAL_COMMERCIAL"` or a different spelling
- Result: `UNMATCHED_CONTAINER` despite correct container match

There is **no mapping table** between these two code sets.

**What's needed:**
- A `charge_code_harmonization` table that maps extraction codes ↔ ERP charge_types
- Step 9 should use this mapping in its fuzzy fallback before rejecting
- The 155-code engine in `engines/parsing/charge_code_normalization/` should be the single source of truth for code resolution, not the hardcoded 29-code map

### Gap 2: Equipment Type Standardization

- Extraction engine outputs: `FRONT_LOAD`, `CART`, `OPEN_TOP`, `ROLL_OFF`, `COMPACTOR`
- ERP stores: `equipment_type` from `services_current` (raw ERP format)
- `normalize_charges.py` maps these to a third vocabulary (`EQUIP_TYPE_MAP` → container_type like "Front Load", "Tote", "Open Top")

Three competing representations, no canonical junction.

**What's needed:**
- A single equipment type resolution table
- Extraction output and ERP catalog must agree on values before Step 9 comparison

### Gap 3: No Feedback Loop

When Step 9/10 produces `UNMATCHED_CONTAINER` or `RATE_VARIANCE`, the failure data stays in `ip_invoice_line_item.status`. It is **never fed back** to:
- The extraction engine (to fix patterns)
- The charge code map (to add missing codes)
- The service catalog (to update stale rates)

**What's needed:**
- Export unmatched/variance results in a format the extraction engine can consume
- Use reconciliation failures to identify:
  - Missing charge codes in the normalization map
  - Equipment type mismatches between extraction and ERP
  - Stale catalog rates that need updating
  - Vendor-specific charge code aliases

---

## Data Flow: Current vs Target

### Current (Disconnected)

```
extraction/executor.py
    ↓ produces ip_charge with charge_code from 29-code map
    ↓
pipeline/catalog_seeder.py
    ↓ builds ip_service_catalog with charge_type from ERP
    ↓
pipeline/step_runner.py Step 9
    ↓ matches on (equipment_type, equipment_size, material)
    ↓ charge_type mismatch → UNMATCHED_CONTAINER
    ↓
    ✕  Dead end — no feedback to extraction
```

### Target (Integrated)

```
extraction/executor.py
    ↓ produces ip_charge with charge_code from unified normalization
    ↓
charge_code_harmonization (NEW)
    ↓ maps extraction charge_code → ERP charge_type
    ↓
pipeline/catalog_seeder.py
    ↓ builds ip_service_catalog with harmonized charge_type
    ↓
pipeline/step_runner.py Step 9
    ↓ matches on (equipment_type, equipment_size, material, charge_type)
    ↓ uses harmonization table for fuzzy fallback
    ↓
pipeline/step_runner.py Step 10
    ↓ variance detection with expected_rate
    ↓
feedback_loop (NEW)
    ↓ routes unmatched → extraction fixes
    ↓ routes variance → catalog updates
    ↓ routes new codes → harmonization table
    ↓
    ◄── Closes the loop
```

---

## Key Files to Study

| File | What It Does | Why It Matters |
|------|-------------|----------------|
| `extraction/normalize_charges.py:67-98` | The 29-code CHARGE_CODE_MAP | Source of the extraction vocabulary |
| `extraction/executor.py` | Pattern executor + handler registry | How charges are extracted from OCR |
| `extraction/output/charge_code_ref.csv` | 171 canonical charge codes | The broader charge code universe |
| `pipeline/catalog_seeder.py` | Builds ip_service_catalog from ERP | Source of the ERP vocabulary |
| `pipeline/step_runner.py` (Step 9) | Catalog matching logic | Where the mismatch manifests |
| `pipeline/step_runner.py` (Step 10) | Variance detection | Where rate discrepancies surface |
| `engines/parsing/charge_code_normalization/` | 155-code normalization engine | The most complete code mapping (not wired to catalog) |
| `SCHEMA.md` (A10, A11) | ip_service_catalog + ip_invoice_line_item | The tables that store reconciliation state |

---

## Scope for Productionization

### Phase 1: Harmonization Table
- Build `charge_code_harmonization` mapping extraction codes ↔ ERP charge_types
- Wire the 155-code normalization engine into the catalog match (replace hardcoded 29-code map)
- Add equipment type resolution table

### Phase 2: Catalog Match Enhancement
- Add charge_type to Step 9 matching criteria (after harmonization)
- Implement charge code alias resolution in fuzzy fallback
- Validate material values against `waste_stream_ref` at match time

### Phase 3: Feedback Loop
- Surface unmatched/variance results to extraction layer
- Auto-detect missing charge codes and queue for HITL resolution
- Track catalog freshness (stale expected_rate detection)
- Close the loop: reconciliation results → extraction pattern fixes → re-run

### Phase 4: Production Hardening
- Batch operation compliance (all writes via execute_values, page_size=1000)
- Pipeline run tracking with step timings and status
- Audit trail: every reconciliation action → ip_pipeline_event
- Error recovery: SAVEPOINT-based atomic rebuilds per step
