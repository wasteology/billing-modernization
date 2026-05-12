"""Tate Services charge extraction."""
import re
from typing import List
from ..models import ChargeItem

def extract_tate_services(text: str) -> List[ChargeItem]:
    items = []
    service_pattern = re.compile(
        r'\d{2}/\d{2}/\d{4}\s+'
        r'((?:SWAP|HAUL|DELIVERY|DUMP|EXCHANGE|FINAL|REMOVAL|PICK\s*UP|RETURN|SWITCH|LIVE\s*LOAD|TRIP)\s*[\w\s\-]+?(?:ROLL\s*OFF|OPEN\s*TOP|COMPACTOR)?[\w\s]*?)'
        r'(?:\s*-\s*WO:\s*\d+)?\s+(\d+\.?\d*)\s+\$?([\d,]+\.?\d+)\s+\$?([\d,]+\.\d{2})',
        re.IGNORECASE
    )
    for m in service_pattern.finditer(text):
        items.append(ChargeItem(
            charge_description=m.group(1).strip(),
            amount=float(m.group(4).replace(',', '')),
            qty=float(m.group(2)) if float(m.group(2)) != 1.0 else None,
            unit_price=float(m.group(3).replace(',', '')),
            raw_text=m.group(0).strip()
        ))
    surcharge = re.compile(r'((?:FUEL|ENVIRONMENTAL|ENERGY)\s*(?:SURCHARGE|FEE)[\w\s]*?)\s+\$?([\d,]+\.\d{2})', re.IGNORECASE)
    for m in surcharge.finditer(text):
        items.append(ChargeItem(charge_description=m.group(1).strip(), amount=float(m.group(2).replace(',', ''))))
    return items
