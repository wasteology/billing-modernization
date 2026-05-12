"""Modern Disposal charge extraction."""
import re
from typing import List
from ..models import ChargeItem

def extract_modern_disposal(text: str) -> List[ChargeItem]:
    items = []
    service_pattern = re.compile(
        r'\d{2}/\d{2}/\d{2,4}\s*-\s*\d{2}/\d{2}/\d{2,4}\s+(\d+)\s*-\s*([\w\s\-/&,]+?)\s*-?\s*\$?([\d,]+\.?\d*)\s+(?:PO#?\s*\d+\s+)?\$?([\d,]+\.\d{2})',
        re.IGNORECASE
    )
    for m in service_pattern.finditer(text):
        items.append(ChargeItem(
            charge_description=m.group(2).strip().rstrip('-').strip(),
            amount=float(m.group(4).replace(',', '')),
            qty=float(m.group(1)) if int(m.group(1)) > 1 else None,
            raw_text=m.group(0).strip()
        ))
    pct_pattern = re.compile(
        r'((?:ENVIRONMENTAL|FUEL|ENERGY|ADMIN|REGULATORY)\s*(?:REGULATORY\s*)?(?:FEE|SURCHARGE|CHARGE))\s+([\d.]+)%\s+\$?([\d,]+\.\d{2})',
        re.IGNORECASE
    )
    for m in pct_pattern.finditer(text):
        items.append(ChargeItem(charge_description=f"{m.group(1).strip()} {m.group(2)}%", amount=float(m.group(3).replace(',', ''))))
    return items
