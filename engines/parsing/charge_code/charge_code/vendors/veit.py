"""Veit Disposal Systems charge extraction."""
import re
from typing import List
from ..models import ChargeItem

def extract_veit(text: str) -> List[ChargeItem]:
    items = []
    service_pattern = re.compile(
        r'\d{2}\s*-\s*\w{3}\s*\|?\s*(?:R\d|[A-Z]{2})\s*(\d+\.?\d*)\s*[})\]]\s*((?:Truck\s*Time|Final\s*Pull|Exchange|Delivery|Dump\s*&?\s*Return|Switch|Haul|Removal|Live\s*Load|Swap|Pick\s*Up)[\w\s]*?)\s+(\d+\.?\d*)\s+\$?([\d,]+\.?\d*)\s+\$?([\d,]+\.\d{2})',
        re.IGNORECASE
    )
    for m in service_pattern.finditer(text):
        items.append(ChargeItem(
            charge_description=f"{m.group(1)}YD {m.group(2).strip()}",
            amount=float(m.group(5).replace(',', '')),
            qty=float(m.group(3)) if float(m.group(3)) != 1.0 else None,
            unit_price=float(m.group(4).replace(',', '')),
            raw_text=m.group(0).strip()
        ))
    disposal_pattern = re.compile(
        r'\d{2}\s*-\s*\w{3}\s*\|?\s*(?:[A-Z]{2})\s+([\w\s\-]+?(?:Ton|Disposal)[\w\s]*?)\s+(\d+\.?\d*)\s+\$?([\d,]+\.?\d*)\s+\$?([\d,]+\.\d{2})',
        re.IGNORECASE
    )
    for m in disposal_pattern.finditer(text):
        items.append(ChargeItem(
            charge_description=m.group(1).strip(),
            amount=float(m.group(4).replace(',', '')),
            qty=float(m.group(2)),
            unit_price=float(m.group(3).replace(',', '')),
            raw_text=m.group(0).strip()
        ))
    fuel_pattern = re.compile(r'(?:FS\s+)?(?:Fuel\s*Surcharge)\s+\$?([\d,]+\.\d{2})', re.IGNORECASE)
    for m in fuel_pattern.finditer(text):
        amount = float(m.group(1).replace(',', ''))
        if amount > 0:
            items.append(ChargeItem(charge_description='Fuel Surcharge', amount=amount))
    return items
