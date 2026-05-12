"""Cockey's Enterprises charge extraction."""

import re
from typing import List
from ..models import ChargeItem


def extract_cockeys(text: str) -> List[ChargeItem]:
    """Format: DATE | REF DESCRIPTION QTY AMOUNT BALANCE"""
    items = []

    charge_pattern = re.compile(
        r'(\d{2}/\d{2}/\d{4})\s*\|\s*'
        r'([A-Z])\s+'
        r'((?!PAYMENT)[A-Z][\w\s\-/&]+?)\s+'
        r'(\d+\.?\d*)\s+'
        r'(-?[\d,]+\.?\d*)\s+'
        r'(-?[\d,]+\.?\d*)',
        re.IGNORECASE
    )

    for m in charge_pattern.finditer(text):
        desc = m.group(3).strip()
        qty = float(m.group(4))
        per_unit = float(m.group(5).replace(',', ''))
        extended = float(m.group(6).replace(',', ''))

        if 'PAYMENT' in desc.upper() or per_unit < 0:
            continue

        items.append(ChargeItem(
            charge_description=desc,
            amount=extended,
            qty=qty if qty != 1.0 else None,
            unit_price=per_unit if qty > 1 and per_unit != extended else None,
            raw_text=m.group(0).strip()
        ))

    fuel_match = re.search(r'Fuel\s+Surcharge\s+(-?[\d,]+\.?\d*)', text, re.IGNORECASE)
    if fuel_match:
        amount = float(fuel_match.group(1).replace(',', ''))
        if amount > 0:
            items.append(ChargeItem(charge_description='Fuel Surcharge', amount=amount))

    return items
