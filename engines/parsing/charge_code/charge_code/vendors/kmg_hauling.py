"""KMG Hauling charge extraction."""
import re
from typing import List
from ..models import ChargeItem

def extract_kmg_hauling(text: str) -> List[ChargeItem]:
    items = []
    service_pattern = re.compile(
        r'\d{1,2}/\d{1,2}/\d{2,4}\s*-\s*\d{1,2}/\d{1,2}/\d{2,4}\s+([\w\s/\-&]+?)\s+(\d+\.?\d*)\s+\$?([\d,]+\.?\d*)\s+\$?([\d,]+\.\d{2})',
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
    surcharge_pattern = re.compile(
        r'((?:ECONOMIC|FUEL|ENVIRONMENTAL|ENERGY|ADMIN|REGULATORY)\s+(?:ADJUSTMENT|SURCHARGE|FEE|CHARGE|RECOVERY)[\w\s]*?)\s+\$?([\d,]+\.\d{2})',
        re.IGNORECASE
    )
    for m in surcharge_pattern.finditer(text):
        items.append(ChargeItem(charge_description=m.group(1).strip(), amount=float(m.group(2).replace(',', ''))))
    return items
