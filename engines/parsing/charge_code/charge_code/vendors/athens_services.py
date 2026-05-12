"""Athens Services charge extraction."""
import re
from typing import List
from ..models import ChargeItem

def extract_athens_services(text: str) -> List[ChargeItem]:
    items = []
    service_pattern = re.compile(
        r'\d{2}/\d{2}/\d{4}\s+(\d+YD[\w\s\-/]+(?:R/O|ROLL|HAUL|DUMP|SWAP|DELIVERY|REMOVAL|EXCHANGE)[\w\s\-]*?)\s+(\d+\.?\d*)\s+\$?([\d,]+\.\d{2})',
        re.IGNORECASE
    )
    for m in service_pattern.finditer(text):
        items.append(ChargeItem(
            charge_description=m.group(1).strip(),
            amount=float(m.group(3).replace(',', '')),
            qty=float(m.group(2)) if float(m.group(2)) != 1.0 else None,
            raw_text=m.group(0).strip()
        ))
    disposal_pattern = re.compile(
        r'\d{2}/\d{2}/\d{4}\s+(DISPOSAL\s+FEE[\w\s\-]*?)\s+(?:TKT#?\s*\d+\s+)?(\d+\.?\d*)\s+\$?([\d,]+\.\d{2})',
        re.IGNORECASE
    )
    for m in disposal_pattern.finditer(text):
        tons = float(m.group(2))
        amount = float(m.group(3).replace(',', ''))
        items.append(ChargeItem(
            charge_description=m.group(1).strip(),
            amount=amount,
            qty=tons,
            unit_price=round(amount / tons, 2) if tons > 0 else None,
            raw_text=m.group(0).strip()
        ))
    late_pattern = re.compile(r'(LATE\s+FEE)\s+\$?([\d,]+\.\d{2})', re.IGNORECASE)
    for m in late_pattern.finditer(text):
        items.append(ChargeItem(charge_description='Late Fee', amount=float(m.group(2).replace(',', ''))))
    return items
