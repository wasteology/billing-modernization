"""Waste Masters charge extraction."""
import re
from typing import List
from ..models import ChargeItem

def extract_waste_masters(text: str) -> List[ChargeItem]:
    items = []
    service_pattern = re.compile(
        r'\d{2}\s*-\s*\w{3}\s+(Monthly\s+Svc:\s*[\w\s\-/&]+?)\s+\$?([\d,]+\.?\d*)\s+(\d+\.?\d*)\s+\$?([\d,]+\.\d{2})',
        re.IGNORECASE
    )
    for m in service_pattern.finditer(text):
        items.append(ChargeItem(
            charge_description=m.group(1).strip(),
            amount=float(m.group(4).replace(',', '')),
            qty=float(m.group(3)) if float(m.group(3)) != 1.0 else None,
            unit_price=float(m.group(2).replace(',', '')),
            raw_text=m.group(0).strip()
        ))
    fee = re.compile(r'((?:FUEL|ENVIRONMENTAL|ENERGY|ADMIN|REGULATORY)\s*(?:SURCHARGE|FEE|CHARGE)[\w\s]*?)\s+\$?([\d,]+\.\d{2})', re.IGNORECASE)
    for m in fee.finditer(text):
        items.append(ChargeItem(charge_description=m.group(1).strip(), amount=float(m.group(2).replace(',', ''))))
    return items
