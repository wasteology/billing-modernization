"""ACE Recycling and Disposal charge extraction."""
import re
from typing import List
from ..models import ChargeItem

def extract_ace_recycling(text: str) -> List[ChargeItem]:
    items = []
    service_pattern = re.compile(
        r'\d{2}/\d{2}/\d{2,4}\s*-\s*\d{2}/\d{2}/\d{2,4}\s+([\w\s\-/&]+?)\s+(\d+\.?\d*)\s+\$?\s*([\d,]+\.?\d*)\s+per\s+month\s+(-?[\d,]+\.\d{2})',
        re.IGNORECASE
    )
    for m in service_pattern.finditer(text):
        items.append(ChargeItem(
            charge_description=m.group(1).strip(),
            amount=float(m.group(4).replace(',', '')),
            qty=float(m.group(2)) if float(m.group(2)) != 1.0 else None,
            unit_price=float(m.group(3).replace(',', '')),
            raw_text=m.group(0).strip()
        ))
    if not items:
        simple = re.compile(
            r'\d{2}/\d{2}/\d{2,4}\s*-\s*\d{2}/\d{2}/\d{2,4}\s+([\w\s\-/&]+?)\s+(\d+\.?\d*)\s+\$?\s*([\d,]+\.?\d*)\s+(-?[\d,]+\.\d{2})',
            re.IGNORECASE
        )
        for m in simple.finditer(text):
            desc = m.group(1).strip()
            if any(w in desc.upper() for w in ['TAX', 'TOTAL', 'BALANCE', 'PAYMENT', 'ACH']):
                continue
            items.append(ChargeItem(charge_description=desc, amount=float(m.group(4).replace(',', '')), qty=float(m.group(2)) if float(m.group(2)) != 1.0 else None))
    return items
