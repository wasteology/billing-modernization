"""Jamaica Ash & Rubbish Removal charge extraction."""
import re
from typing import List
from ..models import ChargeItem

def extract_jamaica_ash(text: str) -> List[ChargeItem]:
    items = []
    service_pattern = re.compile(
        r'\d{2}/\d{2}/\d{2,4}\s*\|\s*[\w]+\s+(\d+)\s+(\d+Y?\s*(?:COMPACTOR|CONTAINER)?[\w\s\-/]*?(?:HAULING|RENTAL|SERVICE|CHARGE|FEE|SURCHARGE)[\w\s]*?)\s+(?:\d+\s+)?(-?[\d,]+\.\d{2})',
        re.IGNORECASE
    )
    for m in service_pattern.finditer(text):
        desc = m.group(2).strip()
        if 'PAYMENT' in desc.upper():
            continue
        items.append(ChargeItem(
            charge_description=desc,
            amount=float(m.group(3).replace(',', '')),
            qty=float(m.group(1)) if int(m.group(1)) > 1 else None,
            raw_text=m.group(0).strip()
        ))
    disposal_pattern = re.compile(
        r'(LANDFILL\s+FEE|DISPOSAL\s+FEE|TIPPING\s+FEE)\s+([\d.]+)\s*tons?\s+([\d.]+)\s*/\s*ton\s+(-?[\d,]+\.\d{2})',
        re.IGNORECASE
    )
    for m in disposal_pattern.finditer(text):
        items.append(ChargeItem(
            charge_description=m.group(1).strip(),
            amount=float(m.group(4).replace(',', '')),
            qty=float(m.group(2)),
            unit_price=float(m.group(3)),
            raw_text=m.group(0).strip()
        ))
    fee_pattern = re.compile(
        r'(FUEL\s*SURCHARGE|ENVIRONMENTAL\s*FEE|FRANCHISE\s*FEE)\s+(?:[\w\s]+\s+)?(-?[\d,]+\.\d{2})',
        re.IGNORECASE
    )
    for m in fee_pattern.finditer(text):
        desc = m.group(1).strip()
        amount = float(m.group(2).replace(',', ''))
        if amount > 0 and not any(i.charge_description.upper() == desc.upper() for i in items):
            items.append(ChargeItem(charge_description=desc, amount=amount))
    return items
