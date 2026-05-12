"""Unique Sanitation charge extraction."""
import re
from typing import List
from ..models import ChargeItem

def extract_unique_sanitation(text: str) -> List[ChargeItem]:
    items = []
    charge_pattern = re.compile(
        r'\d{2}/\d{2}/\d{2,4}\s+(\d+\.?\d*)\s*\|?\s*([\w\s\-/&]+?)\s+(-?[\d,]+\.\d{2})\s+(-?[\d,]+\.\d{2})',
        re.IGNORECASE
    )
    for m in charge_pattern.finditer(text):
        desc = m.group(2).strip()
        if any(w in desc.upper() for w in ['PREVIOUS', 'BALANCE', 'TOTAL', 'TAX', 'SUBTOTAL']):
            continue
        qty = float(m.group(1))
        items.append(ChargeItem(
            charge_description=desc,
            amount=float(m.group(4).replace(',', '')),
            qty=qty if qty != 1.0 else None,
            raw_text=m.group(0).strip()
        ))
    return items
