"""MDI - Mark Dunning Industries charge extraction."""
import re
from typing import List
from ..models import ChargeItem

def extract_mdi(text: str) -> List[ChargeItem]:
    items = []
    service_pattern = re.compile(
        r'\d{2}/\d{2}/\d{2,4}\s+\d+\s+(\d+)\s+([\w\s\-/]+?)\s+\d{2}/\d{2}/\d{2,4}\s*-?\s*(?:\d{2}/\d{2}/\d{2,4})?\s+(-?[\d,]+\.\d{2})',
        re.IGNORECASE
    )
    for m in service_pattern.finditer(text):
        desc = m.group(2).strip()
        if 'PAYMENT' in desc.upper():
            continue
        qty = int(m.group(1))
        items.append(ChargeItem(
            charge_description=desc,
            amount=float(m.group(3).replace(',', '')),
            qty=float(qty) if qty > 1 else None,
            raw_text=m.group(0).strip()
        ))
    if not any('FUEL' in i.charge_description.upper() for i in items):
        fuel = re.compile(r'(FUEL\s*SURCHARGE)\s+\d{2}/\d{2}/\d{2,4}\s+(-?[\d,]+\.\d{2})', re.IGNORECASE)
        for m in fuel.finditer(text):
            amount = float(m.group(2).replace(',', ''))
            if amount > 0:
                items.append(ChargeItem(charge_description='Fuel Surcharge', amount=amount))
    return items
