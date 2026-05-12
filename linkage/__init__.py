"""
Invoice Linkage — match hauler invoices to billing_charges via business facts.

Replaces the old account_linkage pipeline that went through billing_reference
(which fans out to 1,105+ service_ids on grouped billing).

New approach: vendor + address + amount + date → location_id.

Modules:
  schema.py    — DDL for invoice_registry, invoice_service_match, account_location_map
  address.py   — Address normalization and fuzzy matching utilities
  loader.py    — Pull vw_sharepoint_gapi_all → invoice_registry
  enricher.py  — Run parsing_engines regex against OCR → override fields
  matcher.py   — Match invoice_registry ↔ billing_charges
  resolver.py  — Aggregate matches → account_location_map

Usage:
    from src.invoice_linkage.loader import load_invoice_registry
    from src.invoice_linkage.enricher import enrich_invoices
    from src.invoice_linkage.matcher import match_invoices
    from src.invoice_linkage.resolver import resolve_account_locations
"""

# Schema is safe to import eagerly (no dependency on database.py)
from .schema import create_tables as create_linkage_tables


def __getattr__(name):
    """Lazy imports to avoid circular dependency with database.py."""
    if name == "load_invoice_registry":
        from .loader import load_invoice_registry
        return load_invoice_registry
    if name == "enrich_invoices":
        from .enricher import enrich_invoices
        return enrich_invoices
    if name == "match_invoices":
        from .matcher import match_invoices
        return match_invoices
    if name == "resolve_account_locations":
        from .resolver import resolve_account_locations
        return resolve_account_locations
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
