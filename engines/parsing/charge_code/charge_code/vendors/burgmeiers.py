"""Burgmeier's Hauling charge extraction."""
import re
from typing import List
from ..models import ChargeItem

def extract_burgmeiers(text: str) -> List[ChargeItem]:
    items = []
    service_pattern = re.compile(
        r'(\d+\s*(?:YD|YARD|CY)\s+(?:Switch|Exchange|Dump\s*&?\s*Return|Delivery|Final\s*Pull|Haul|Live\s*Load|Removal|Swap|Pick\s*Up))\s+([\d,]+\.?\d*)\s+(\d+)\s+([\d,]+\.\d{2})',
        re.IGNORECASE
    )
    for m in service_pattern.finditer(text):
        items.append(ChargeItem(
            charge_description=m.group(1).strip(),
            amount=float(m.group(4).replace(',', '')),
            qty=float(m.group(3)) if int(m.group(3)) != 1 else None,
            unit_price=float(m.group(2).replace(',', '')),
            raw_text=m.group(0).strip()
        ))
    disposal_pattern = re.compile(
        r'(Disposal\s+(?:by\s+)?Ton)\s+([\d,]+\.?\d*)\s+([\d,]+\.?\d*)\s+([\d,]+\.\d{2})',
        re.IGNORECASE
    )
    for m in disposal_pattern.finditer(text):
        items.append(ChargeItem(
            charge_description='Disposal by Ton',
            amount=float(m.group(4).replace(',', '')),
            qty=float(m.group(3).replace(',', '')),
            unit_price=float(m.group(2).replace(',', '')),
            raw_text=m.group(0).strip()
        ))
    usage_pattern = re.compile(
        r'(usageDays|(?:Daily\s*)?Rental|Container\s*Rent(?:al)?)\s+([\d,]+\.?\d*)\s+(\d+)\s+([\d,]+\.\d{2})',
        re.IGNORECASE
    )
    for m in usage_pattern.finditer(text):
        amount = float(m.group(4).replace(',', ''))
        if amount > 0:
            items.append(ChargeItem(
                charge_description=m.group(1).strip(),
                amount=amount,
                qty=float(m.group(3)),
                unit_price=float(m.group(2).replace(',', '')) if float(m.group(2).replace(',', '')) > 0 else None,
            ))
    return items
