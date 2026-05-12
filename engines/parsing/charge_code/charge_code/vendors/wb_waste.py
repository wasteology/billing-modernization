"""WB Waste Solutions charge extraction."""
import re
from typing import List
from ..models import ChargeItem

def extract_wb_waste(text: str) -> List[ChargeItem]:
    items = []
    service_pattern = re.compile(
        r'\d{2}/\d{2}/\d{4}\s*-\s*\d{2}/\d{2}/\d{4}\s+'
        r'((?:Weekly|Every\s+\d+\s+Weeks?|Monthly|Bi-?Weekly|EOW)\s+)?'
        r'([\w\s\-/&]+?(?:SERVICE|CHARGE|RENTAL|FEE)[\w\s]*?)\s+'
        r'(\d+\.?\d*)\s+\$?([\d,]+\.?\d*)\s+\$?([\d,]+\.\d{2})',
        re.IGNORECASE
    )
    for m in service_pattern.finditer(text):
        freq = (m.group(1) or '').strip()
        desc = m.group(2).strip()
        if freq:
            desc = f"{freq} {desc}"
        items.append(ChargeItem(
            charge_description=desc,
            amount=float(m.group(5).replace(',', '')),
            qty=float(m.group(3)) if float(m.group(3)) != 1.0 else None,
            raw_text=m.group(0).strip()
        ))
    surcharge_pattern = re.compile(
        r'((?:FUEL|ENVIRONMENTAL|ENERGY|ADMIN|REGULATORY|FRANCHISE)\s+(?:SURCHARGE|FEE|CHARGE|TAX)[\w\s]*?)\s+\$?([\d,]+\.\d{2})',
        re.IGNORECASE
    )
    for m in surcharge_pattern.finditer(text):
        amount = float(m.group(2).replace(',', ''))
        if amount > 0:
            items.append(ChargeItem(charge_description=m.group(1).strip(), amount=amount))
    return items
