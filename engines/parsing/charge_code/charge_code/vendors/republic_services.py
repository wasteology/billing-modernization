"""Republic Services charge extraction."""
import re
from typing import List
from ..models import ChargeItem

def extract_republic_services(text: str) -> List[ChargeItem]:
    items = []
    two_line = re.compile(
        r'(\d+)\s+([\w\s]+?(?:Container|Cart|Dumpster|Toter|Compactor)[\w\s/]*?'
        r'(?:\d+[/\d]*\s*(?:Cu\s*Yd|Gal|Yard))?.*?(?:\d+\s*Lift\s*Per\s*\w+)?[^\n]*?)\n\s*'
        r'([\w\s]+?Service[\w\s]*?)\s+'
        r'(\d{2}/\d{2})\s*-\s*(\d{2}/\d{2})\s+'
        r'\$?([\d,]+\.?\d*)\s+\$?([\d,]+\.\d{2})',
        re.IGNORECASE
    )
    for m in two_line.finditer(text):
        items.append(ChargeItem(
            charge_description=f"{m.group(2).strip()} - {m.group(3).strip()}",
            amount=float(m.group(7).replace(',', '')),
            unit_price=float(m.group(6).replace(',', '')),
            raw_text=m.group(0).strip()
        ))
    if not items:
        single = re.compile(
            r'([\w\s\-/,]+?(?:Service|Charge|Fee|Rental|Delivery|Haul|Container|Pickup|Removal|Surcharge)[\w\s]*?)\s+'
            r'(?:\d{2}/\d{2}\s*-\s*\d{2}/\d{2}\s+)?'
            r'\$?([\d,]+\.?\d*)\s+\$?([\d,]+\.\d{2})',
            re.IGNORECASE
        )
        for m in single.finditer(text):
            desc = m.group(1).strip()
            if any(w in desc.upper() for w in ['CURRENT INVOICE', 'TOTAL', 'PREVIOUS', 'PAYMENT']):
                continue
            items.append(ChargeItem(charge_description=desc, amount=float(m.group(3).replace(',', ''))))
    return items
