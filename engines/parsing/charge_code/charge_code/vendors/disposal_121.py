"""121 Disposal charge extraction."""
import re
from typing import List
from ..models import ChargeItem

def extract_disposal_121(text: str) -> List[ChargeItem]:
    items = []
    service_pattern = re.compile(
        r'((?:Rental|Haul|Swap|Delivery|Disposal|Pick\s*Up|Container|Tonnage|Trip|Service|Pull|Exchange)[\w\s\-/&,#.()]+?)\s+(-?[\d,]+\.\d{2})\s*$',
        re.MULTILINE | re.IGNORECASE
    )
    for m in service_pattern.finditer(text):
        desc = m.group(1).strip()
        if any(w in desc.upper() for w in ['SUBTOTAL', 'TOTAL', 'BALANCE', 'CURRENT', 'PREVIOUS']):
            continue
        qty_match = re.search(r'Qty:\s*(\d+)', text[max(0, m.start()-100):m.start()])
        qty = float(qty_match.group(1)) if qty_match else None
        items.append(ChargeItem(charge_description=desc, amount=float(m.group(2).replace(',', '')), qty=qty if qty and qty != 1.0 else None))
    return items
