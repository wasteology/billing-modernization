"""Charge code extraction engine.

Extracts structured charge line items from raw OCR invoice text.
Each vendor has a unique invoice format — no generics.

Usage:
    from parsing_engines.charge_code import extract_charges, ChargeItem

    items = extract_charges('Waste Management', ocr_text)
    for item in items:
        print(item.charge_description, item.amount, item.qty, item.unit_price)
"""

from .models import ChargeItem
from .charge_code_engine import extract_charges, get_vendor_count, get_configured_vendors
from .unified import extract_all_charges

__all__ = [
    'ChargeItem',
    'extract_charges',
    'extract_all_charges',
    'get_vendor_count',
    'get_configured_vendors',
]
