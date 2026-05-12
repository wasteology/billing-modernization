"""Invoice processing subpackage — OCR loading and 10-step pipeline with AI-assisted HITL review.

DB-driven pipeline modules:
- step_runner: Steps 1-10 execution with gate enforcement
- extraction_engine: DB-driven pattern execution from ip_vendor_pattern
- catalog_seeder: Seed ip_service_catalog from ERP data
- ai_suggestions: AI suggestion layer for review queue
- review_resolver: HITL disposition handler (steps 1-10, including line item dispositions)
- reprocess: Re-extraction after pattern deploy
- validators: Per-field validation checks from vendor profiles
- meta_helper: Pattern CRUD with 3-gate validation
- db_helpers: Batched PostgreSQL read/write helpers (line items, catalog, etc.)
- app: HTTP API server for review UI
"""

from .processor import step_ocr, step_vendor, step_account, step_lookup, step_address, review_step, approve_step
from .invoice_renderer import render_review_invoices, save_invoice_image
from .loader import load_ocr_documents, sync_ocr_from_bigquery, backfill_ocr_dates, DEFAULT_CSV
from .suggestions import suggest_vendor, suggest_account, get_account_format_display
