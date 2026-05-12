"""Data models for charge code extraction."""

from dataclasses import dataclass
from typing import Optional


@dataclass
class ChargeItem:
    """Represents a single charge line item extracted from an invoice."""
    charge_description: str            # What the vendor calls it (raw from invoice)
    amount: Optional[float] = None     # Dollar amount
    qty: Optional[float] = None        # Quantity (containers, tons, days, hours, etc.)
    unit_price: Optional[float] = None # Per-unit rate
    raw_text: Optional[str] = None     # Original OCR snippet for debugging
