"""EDCO Waste & Recycling charge extraction."""
import re
from typing import List
from ..models import ChargeItem

def extract_edco(text: str) -> List[ChargeItem]:
    items = []
    charge_pattern = re.compile(r'(\d{2,4})\s+([\w\s$xX\-/&.]+?)\s+(-?[\d,]+\.\d{2})\s*$', re.MULTILINE)
    for m in charge_pattern.finditer(text):
        desc = m.group(2).strip()
        amount = float(m.group(3).replace(',', ''))
        skip = ['FORWARD', 'BALANCE', 'PREVIOUS', 'PAYMENT', 'CURRENT CHARGES', 'TOTAL']
        if any(w in desc.upper() for w in skip) or amount < 0:
            continue
        rate_days = re.search(r'\$?(\d+\.?\d*)\s*[xX]\s*(\d+)\s*DAYS?', desc)
        qty = float(rate_days.group(2)) if rate_days else None
        unit_price = float(rate_days.group(1)) if rate_days else None
        items.append(ChargeItem(charge_description=desc, amount=amount, qty=qty, unit_price=unit_price))
    return items
