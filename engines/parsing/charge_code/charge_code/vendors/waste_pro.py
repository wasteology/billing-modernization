"""Waste Pro charge extraction."""
import re
from typing import List
from ..models import ChargeItem

def extract_waste_pro(text: str) -> List[ChargeItem]:
    items = []
    service_pattern = re.compile(
        r'\d{2}/\d{2}/\d{4}\s*-\s*\d{2}/\d{2}/\d{4}\s+([\w\s\-/&]+?)\s+(\d+\.?\d*)\s+(-?[\d,]+\.\d{2})',
        re.IGNORECASE
    )
    for m in service_pattern.finditer(text):
        desc = m.group(1).strip()
        if 'Invoice #' in desc or 'Payment' in desc:
            continue
        items.append(ChargeItem(
            charge_description=desc,
            amount=float(m.group(3).replace(',', '')),
            qty=float(m.group(2)) if float(m.group(2)) != 1.0 else None,
            raw_text=m.group(0).strip()
        ))
    return items
