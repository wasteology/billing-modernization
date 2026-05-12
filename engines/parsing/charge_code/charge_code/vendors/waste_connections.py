"""Waste Connections charge extraction."""
import re
from typing import List
from ..models import ChargeItem

def extract_waste_connections(text: str) -> List[ChargeItem]:
    items = []
    qty_rate = re.compile(
        r'\d{1,2}/\d{1,2}/\d{4}\s+([\w\s\-/&]+?)\s+\((\d+\.?\d*)\s*@\s*\$?([\d,]+\.?\d*)\)\s+\$?([\d,]+\.\d{2})',
        re.IGNORECASE
    )
    for m in qty_rate.finditer(text):
        qty = float(m.group(2))
        items.append(ChargeItem(
            charge_description=m.group(1).strip(),
            amount=float(m.group(4).replace(',', '')),
            qty=qty if qty != 1.0 else None,
            unit_price=float(m.group(3).replace(',', '')),
            raw_text=m.group(0).strip()
        ))
    if not items:
        simple = re.compile(
            r'\d{1,2}/\d{1,2}/\d{4}\s+([\w\s\-/&]+?(?:FEE|CHARGE|SERVICE|RENTAL|HAUL|DISPOSAL|SURCHARGE|CONTAINER|DELIVERY|PICKUP|REMOVAL)[\w\s]*?)\s+\$?([\d,]+\.\d{2})',
            re.IGNORECASE
        )
        for m in simple.finditer(text):
            desc = m.group(1).strip()
            if any(w in desc.upper() for w in ['PREVIOUS', 'TOTAL', 'PAYMENT']):
                continue
            items.append(ChargeItem(charge_description=desc, amount=float(m.group(2).replace(',', ''))))
    return items
