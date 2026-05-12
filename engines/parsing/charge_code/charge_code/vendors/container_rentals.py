"""Container Rentals charge extraction."""
import re
from typing import List
from ..models import ChargeItem

def _extract_container_rentals_format(text: str) -> List[ChargeItem]:
    items = []
    line_pattern = re.compile(
        r'\d{1,2}/\d{1,2}\s+([\w\s\-/&:.,%()+]+?)\s+(\d+\.?\d*)\s+([\d,]+\.?\d*)\s+([\d,]+\.\d{2})',
        re.IGNORECASE
    )
    for m in line_pattern.finditer(text):
        desc = m.group(1).strip()
        if any(w in desc.upper() for w in ['SUB TOTAL', 'TOTAL', 'PAYMENT', 'OPEN BALANCE']):
            continue
        qty = float(m.group(2))
        items.append(ChargeItem(
            charge_description=desc,
            amount=float(m.group(4).replace(',', '')),
            qty=qty if qty != 1.0 else None,
            unit_price=float(m.group(3).replace(',', '')),
            raw_text=m.group(0).strip()
        ))
    return items

def extract_container_rentals(text: str) -> List[ChargeItem]:
    return _extract_container_rentals_format(text)
