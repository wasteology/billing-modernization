"""Universal Waste Systems charge extraction."""
import re
from typing import List
from ..models import ChargeItem

def extract_universal_waste(text: str) -> List[ChargeItem]:
    items = []
    service_pattern = re.compile(
        r'(\d{2}/\d{2}/\d{2,4})\s*-\s*(\d{2}/\d{2}/\d{2,4})\s+(\d+)\s+([\w\s\-.&/]+?)\s+(-?[\d,]+\.\d{2})\s+(-?[\d,]+\.\d{2})',
        re.IGNORECASE
    )
    for m in service_pattern.finditer(text):
        qty = int(m.group(3))
        items.append(ChargeItem(
            charge_description=m.group(4).strip(),
            amount=float(m.group(6).replace(',', '')),
            qty=float(qty) if qty > 1 else None,
            unit_price=float(m.group(5).replace(',', '')) if qty > 1 else None,
            raw_text=m.group(0).strip()
        ))
    adj_pattern = re.compile(
        r'(\d{2}/\d{2}/\d{2,4})\s+(\d+)\s+((?:Price\s+Increase|Adjustment|Correction|Credit)[\w\s\-.]*?)\s+(-?[\d,]+\.\d{2})\s+(-?[\d,]+\.\d{2})',
        re.IGNORECASE
    )
    for m in adj_pattern.finditer(text):
        extended = float(m.group(5).replace(',', ''))
        if not any(abs(i.amount - extended) < 0.01 for i in items if i.amount is not None):
            items.append(ChargeItem(charge_description=m.group(3).strip(), amount=extended))
    return items
