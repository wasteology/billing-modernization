"""Parish Disposal charge extraction."""
import re
from typing import List
from ..models import ChargeItem

def extract_parish_disposal(text: str) -> List[ChargeItem]:
    items = []
    charges_section = re.search(r'Charges\s*\n(.*?)(?:BALANCE\s*DUE|Subtotal|Total)', text, re.DOTALL | re.IGNORECASE)
    search_text = charges_section.group(1) if charges_section else text
    charge_pattern = re.compile(r'(\d+)\s+([\w\s\-/&,]+?)\s+([\d,]+\.?\d*)\s+([\d,]+\.\d{2})', re.IGNORECASE)
    for m in charge_pattern.finditer(search_text):
        qty = int(m.group(1))
        desc = m.group(2).strip()
        if any(w in desc.upper() for w in ['INVOICE', 'DATE', 'TOTAL', 'BALANCE', 'ACCOUNT']):
            continue
        items.append(ChargeItem(
            charge_description=desc,
            amount=float(m.group(4).replace(',', '')),
            qty=float(qty) if qty > 1 else None,
            unit_price=float(m.group(3).replace(',', '')) if qty > 1 else None,
            raw_text=m.group(0).strip()
        ))
    return items
