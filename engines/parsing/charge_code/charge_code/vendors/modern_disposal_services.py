"""Modern Disposal Services charge extraction."""
import re
from typing import List
from ..models import ChargeItem

def extract_modern_disposal_services(text: str) -> List[ChargeItem]:
    items = []
    subitem_pattern = re.compile(r'(\d+\.?\d*)\s*-\s*([\w\s\-/&]+?)\s*-\s*\$?([\d,]+\.\d{2})', re.IGNORECASE)
    for m in subitem_pattern.finditer(text):
        qty = float(m.group(1))
        desc = m.group(2).strip()
        rate = float(m.group(3).replace(',', ''))
        if any(w in desc.upper() for w in ['DISPOSAL', 'TRASH', 'DEBRIS', 'MSW', 'RECYCL']):
            amount = round(qty * rate, 2)
        else:
            amount = rate
        items.append(ChargeItem(charge_description=desc, amount=amount, qty=qty if qty != 1.0 else None, unit_price=rate))
    pct_pattern = re.compile(
        r'((?:ENVIRONMENTAL|FUEL|ENERGY|ADMIN|REGULATORY)\s*(?:REGULATORY\s*)?(?:FEE|SURCHARGE|CHARGE))\s+([\d.]+)%\s+\$?([\d,]+\.\d{2})',
        re.IGNORECASE
    )
    for m in pct_pattern.finditer(text):
        items.append(ChargeItem(charge_description=f"{m.group(1).strip()} {m.group(2)}%", amount=float(m.group(3).replace(',', ''))))
    return items
