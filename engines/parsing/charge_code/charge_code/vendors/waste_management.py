"""Waste Management charge extraction."""

import re
from typing import List
from ..models import ChargeItem


def extract_waste_management(text: str) -> List[ChargeItem]:
    """Extract charge items from Waste Management invoice OCR text.
    
    Format: DATE MATERIAL QTY DESCRIPTION PRICE TAX AMOUNT
    e.g. "12/01/2024 Trash 1.00 Pickup 3 Yards Trash DMP Weekly x1 218.09 0.00 218.09"
    """
    items = []

    charge_pattern = re.compile(
        r'(\d{2}/\d{2}/\d{4})\s+'
        r'(\w[\w\s]*?)\s+'
        r'(\d+\.?\d*)\s+'
        r'(.*?)\s+'
        r'(-?[\d,]+\.?\d*)\s+'
        r'(-?[\d,]+\.?\d*)\s+'
        r'(-?[\d,]+\.?\d*)\s*$',
        re.MULTILINE
    )

    for m in charge_pattern.finditer(text):
        desc_raw = m.group(4).strip()
        qty = float(m.group(3))
        unit_price = float(m.group(5).replace(',', ''))
        amount = float(m.group(7).replace(',', ''))

        if amount == 0 and unit_price == 0 and qty == 0:
            continue

        material = m.group(2).strip()
        description = desc_raw
        if material and material.lower() not in desc_raw.lower():
            description = f"{material} - {desc_raw}"

        items.append(ChargeItem(
            charge_description=description,
            amount=amount if amount != 0 else unit_price,
            qty=qty if qty != 0 else None,
            unit_price=unit_price if unit_price != 0 else None,
            raw_text=m.group(0).strip()
        ))

    if not items:
        fallback = re.compile(
            r'((?:Pickup|Delivery|Removal|Container|Rental|Landfill|'
            r'Government|Admin|Fuel|Energy|Environmental|Regulatory)\s.*?)'
            r'\s+(-?[\d,]+\.\d{2})\s+[\d,]+\.\d{2}\s+(-?[\d,]+\.\d{2})',
            re.IGNORECASE
        )
        for m in fallback.finditer(text):
            items.append(ChargeItem(
                charge_description=m.group(1).strip(),
                amount=float(m.group(3).replace(',', '')),
                raw_text=m.group(0).strip()
            ))

    return items
