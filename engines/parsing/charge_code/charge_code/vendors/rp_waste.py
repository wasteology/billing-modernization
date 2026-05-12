"""RP Waste charge extraction."""
import re
from typing import List
from ..models import ChargeItem

def extract_rp_waste(text: str) -> List[ChargeItem]:
    items = []
    charge_pattern = re.compile(
        r'([\w\s\-/&,]+?(?:container|dumpster|haul|disposal|swap|delivery|rental|pull|tonnage|service|fee|surcharge|charge)[\w\s]*?)\s+'
        r'(\d+)\s+\$?([\d,]+\.?\d*)\s+(?:[\d.]+%\s+)?\$?([\d,]+\.\d{2})',
        re.IGNORECASE
    )
    for m in charge_pattern.finditer(text):
        desc = m.group(1).strip()
        if any(w in desc.upper() for w in ['SUBTOTAL', 'TOTAL', 'BALANCE']):
            continue
        qty = int(m.group(2))
        items.append(ChargeItem(
            charge_description=desc,
            amount=float(m.group(4).replace(',', '')),
            qty=float(qty) if qty > 1 else None,
            unit_price=float(m.group(3).replace(',', '')),
            raw_text=m.group(0).strip()
        ))
    return items
