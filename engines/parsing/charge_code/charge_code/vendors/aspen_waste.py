"""Aspen Waste Systems charge extraction."""
import re
from typing import List
from ..models import ChargeItem

def extract_aspen_waste(text: str) -> List[ChargeItem]:
    items = []
    line_pattern = re.compile(
        r'\d{2}/\d{2}/\d{2,4}\s+([\w\s/\-.&,]+?)\s+(-?[\d,]+\.\d{2})\s*$',
        re.MULTILINE
    )
    for m in line_pattern.finditer(text):
        desc = m.group(1).strip()
        amount = float(m.group(2).replace(',', ''))
        skip = ['WORK ORDER', 'PAGE', 'INVOICE', 'DATE', 'AMOUNT', 'PLEASE PAY', 'TOTAL', 'BALANCE', 'DUE']
        if any(w in desc.upper() for w in skip):
            continue
        desc = re.sub(r'\s+(?:ca|cr|db)\s*$', '', desc, flags=re.IGNORECASE).strip()
        if desc and amount != 0:
            items.append(ChargeItem(charge_description=desc, amount=amount, raw_text=m.group(0).strip()))
    return items
