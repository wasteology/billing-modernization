"""The Arc of The St Johns charge extraction."""
import re
from typing import List
from ..models import ChargeItem

def extract_the_arc(text: str) -> List[ChargeItem]:
    items = []
    items_section = re.search(r'(?:Quantity|Item|Rate|Amount)\s*\n(.*?)(?:Total|Subtotal|Please)', text, re.DOTALL | re.IGNORECASE)
    search_text = items_section.group(1) if items_section else text
    charge_pattern = re.compile(r'(\d+)\s+([\w\s\-/&,#.]+?)\s+\$?([\d,]+\.?\d*)\s+\$?([\d,]+\.\d{2})', re.IGNORECASE)
    for m in charge_pattern.finditer(search_text):
        desc = m.group(2).strip()
        if any(w in desc.upper() for w in ['TOTAL', 'TAX', 'SUBTOTAL', 'DUE', 'INVOICE']):
            continue
        if len(desc) > 2:
            qty = int(m.group(1))
            items.append(ChargeItem(
                charge_description=desc,
                amount=float(m.group(4).replace(',', '')),
                qty=float(qty) if qty > 1 else None,
                unit_price=float(m.group(3).replace(',', '')),
                raw_text=m.group(0).strip()
            ))
    return items
