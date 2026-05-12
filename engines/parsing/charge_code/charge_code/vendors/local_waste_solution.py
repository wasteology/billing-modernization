"""Local Waste Solution charge extraction."""
import re
from typing import List
from ..models import ChargeItem

def extract_local_waste_solution(text: str) -> List[ChargeItem]:
    items = []
    normalized = re.sub(r'\bO(\d)', r'0\1', text)
    service_pattern = re.compile(
        r'\d{2}/\d{2}/\d{2,4}\s+([\w\s/\-]+?)\s+#\s*P/?U:?\s*(\d+)\s+(\d+\.?\d*)\s+(-?[\d,]+\.\d{2})',
        re.IGNORECASE
    )
    for m in service_pattern.finditer(normalized):
        items.append(ChargeItem(
            charge_description=f"{m.group(1).strip()} #P/U: {int(m.group(2))}",
            amount=float(m.group(4).replace(',', '')),
            qty=float(m.group(3)) if float(m.group(3)) != 1.0 else None,
            raw_text=m.group(0).strip()
        ))
    fee_pattern = re.compile(
        r'\d{2}/\d{2}/\d{2,4}\s+((?:LATE|FUEL|ENVIRONMENTAL|ENERGY|ADMIN|FRANCHISE|CONTAINER|RENTAL|DELIVERY|EXTRA)\s*(?:FEE|SURCHARGE|CHARGE)?[\w\s]*?)\s+(-?[\d,]+\.\d{2})',
        re.IGNORECASE
    )
    for m in fee_pattern.finditer(normalized):
        desc = m.group(1).strip()
        if not any(desc in i.charge_description for i in items):
            items.append(ChargeItem(charge_description=desc, amount=float(m.group(2).replace(',', ''))))
    return items
