"""SBC Waste Solutions charge extraction."""
import re
from typing import List
from ..models import ChargeItem

def extract_sbc_waste(text: str) -> List[ChargeItem]:
    items = []
    charge_pattern = re.compile(
        r'\d{2}/\d{2}/\d{2,4}\s+([\w\s\-/&]+?)\s+(\d+\.?\d*)\s+(\d+\.?\d+)\s+\$?(-?[\d,]+\.\d{2})',
        re.IGNORECASE
    )
    for m in charge_pattern.finditer(text):
        desc = m.group(1).strip()
        amount = float(m.group(4).replace(',', ''))
        if 'PMT' in desc.upper() or 'PAYMENT' in desc.upper() or amount < 0:
            continue
        units = float(m.group(2))
        rate = float(m.group(3))
        items.append(ChargeItem(
            charge_description=desc, amount=amount,
            qty=units if units != 1.0 else None,
            unit_price=rate if units > 1 else None,
            raw_text=m.group(0).strip()
        ))
    simple = re.compile(r'\d{2}/\d{2}/\d{2,4}\s+([\w\s\-/&]+?)\s+(\d+\.?\d*)\s+\$(-?[\d,]+\.\d{2})\s*$', re.MULTILINE)
    for m in simple.finditer(text):
        desc = m.group(1).strip()
        amount = float(m.group(3).replace(',', ''))
        if 'PMT' in desc.upper() or 'PAYMENT' in desc.upper() or amount < 0:
            continue
        if any(abs(i.amount - amount) < 0.01 and i.charge_description == desc for i in items if i.amount is not None):
            continue
        items.append(ChargeItem(charge_description=desc, amount=amount))
    compliance = re.compile(r'(BUS\.?\s*COMPLIANCE)\s+\$?([\d,]+\.\d{2})', re.IGNORECASE)
    for m in compliance.finditer(text):
        amount = float(m.group(2).replace(',', ''))
        if amount > 0:
            items.append(ChargeItem(charge_description='Business Compliance', amount=amount))
    return items
