"""Robinson Waste Services charge extraction."""

import re
from typing import List
from ..models import ChargeItem


def extract_robinson_waste(text: str) -> List[ChargeItem]:
    """Format: DD - Mon Dump & Return W.O# NNNNNN QTY RATE AMOUNT"""
    items = []

    haul_pattern = re.compile(
        r'(\d{2})\s*-\s*(\w{3})\s+'
        r'((?:Dump\s*&?\s*Return|Switch|Exchange|Delivery|Final\s*Pull|'
        r'Haul|Live\s*Load|Swap|Pick\s*Up|Removal|Extra\s*P/?U|Trip\s*Charge)[\w\s]*?)\s+'
        r'(?:W\.?O\.?#?\s*(\d+)\s+)?'
        r'(\d+\.?\d*)\s+'
        r'\$?([\d,]+\.?\d*)\s+'
        r'\$?([\d,]+\.\d{2})',
        re.IGNORECASE
    )

    for m in haul_pattern.finditer(text):
        desc = m.group(3).strip()
        wo = m.group(4)
        if wo:
            desc = f"{desc} WO#{wo}"
        items.append(ChargeItem(
            charge_description=desc,
            amount=float(m.group(7).replace(',', '')),
            qty=float(m.group(5)) if float(m.group(5)) != 1.0 else None,
            unit_price=float(m.group(6).replace(',', '')),
            raw_text=m.group(0).strip()
        ))

    disposal_pattern = re.compile(
        r'(\d{2})\s*-\s*(\w{3})\s+'
        r'([\w\s/&\-]+?Disposal[\w\s]*?)\s+'
        r'(?:[\d\-]+\s+)?'
        r'\$?([\d,]+\.\d{2})',
        re.IGNORECASE
    )

    for m in disposal_pattern.finditer(text):
        items.append(ChargeItem(
            charge_description=m.group(3).strip(),
            amount=float(m.group(4).replace(',', '')),
            raw_text=m.group(0).strip()
        ))

    surcharge_pattern = re.compile(
        r'((?:Fuel|Environmental|Energy|Admin|Regulatory)\s*'
        r'(?:Surcharge|Fee|Charge|Recovery)[\w\s]*?)\s+'
        r'\$?([\d,]+\.\d{2})',
        re.IGNORECASE
    )
    for m in surcharge_pattern.finditer(text):
        desc = m.group(1).strip()
        amount = float(m.group(2).replace(',', ''))
        if not any(i.charge_description == desc and i.amount == amount for i in items):
            items.append(ChargeItem(charge_description=desc, amount=amount))

    return items
