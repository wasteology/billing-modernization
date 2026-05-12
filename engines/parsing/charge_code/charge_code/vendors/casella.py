"""Casella Waste Systems charge extraction."""
import re
from typing import List
from ..models import ChargeItem

def extract_casella(text: str) -> List[ChargeItem]:
    items = []
    service_pattern = re.compile(
        r'\d{1,2}/\d{1,2}/\d{2,4}\s+([\w\s/\-]+?)\s+#\s*P/?U:?\s*(\d+)\s+(\d+\.?\d*)\s+(-?[\d,]+\.\d{2})',
        re.IGNORECASE
    )
    for m in service_pattern.finditer(text):
        items.append(ChargeItem(
            charge_description=f"{m.group(1).strip()} #P/U: {int(m.group(2)):02d}",
            amount=float(m.group(4).replace(',', '')),
            qty=float(m.group(3)) if float(m.group(3)) != 1.0 else None,
            raw_text=m.group(0).strip()
        ))
    fee_pattern = re.compile(r'Total\s+([\w\s&/.]+?Fee[\w\s]*?):\s*(-?[\d,]+\.\d{2})', re.IGNORECASE)
    for m in fee_pattern.finditer(text):
        amount = float(m.group(2).replace(',', ''))
        if amount > 0:
            items.append(ChargeItem(charge_description=m.group(1).strip(), amount=amount))
    return items
