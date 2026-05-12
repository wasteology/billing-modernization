"""EASCO Brokerage charge extraction."""
import re
from typing import List
from ..models import ChargeItem

def extract_easco_brokerage(text: str) -> List[ChargeItem]:
    items = []
    detail = re.search(r'(?:Northrop\s+Grumman|Memo\s+Item)\s*\n(.*?)(?:TOTAL|Page)', text, re.DOTALL | re.IGNORECASE)
    search_text = detail.group(1) if detail else text
    charge_pattern = re.compile(r'([\w\s.]+?)\s+([\d,]+)\s+([\d.]+)\s+([\d,]+\.\d{2})', re.IGNORECASE)
    for m in charge_pattern.finditer(search_text):
        desc = m.group(1).strip()
        if any(w in desc.upper() for w in ['TOTAL', 'PAGE', 'DATE']):
            continue
        if len(desc) > 1:
            items.append(ChargeItem(
                charge_description=desc,
                amount=float(m.group(4).replace(',', '')),
                qty=float(m.group(2).replace(',', '')),
                unit_price=float(m.group(3)),
                raw_text=m.group(0).strip()
            ))
    return items
