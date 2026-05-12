"""Check Sammy charge extraction."""
import re
from typing import List
from ..models import ChargeItem

def extract_check_sammy(text: str) -> List[ChargeItem]:
    items = []
    charge_pattern = re.compile(
        r'((?:Commercial|Residential|Junk|Bulk|E-?Waste|Recycling|Mattress|Appliance|Furniture|Debris|Hauling|Removal|Dumpster|Clean\s*Out|Roll\s*Off|Late|Trip|Cancellation)[\w\s\-#/&,.]*?)\s+'
        r'(\d+)\s+\$?([\d,]+\.?\d*)\s+\$?([\d,]+\.\d{2})',
        re.IGNORECASE
    )
    for m in charge_pattern.finditer(text):
        qty = int(m.group(2))
        items.append(ChargeItem(
            charge_description=m.group(1).strip(),
            amount=float(m.group(4).replace(',', '')),
            qty=float(qty) if qty > 1 else None,
            unit_price=float(m.group(3).replace(',', '')),
            raw_text=m.group(0).strip()
        ))
    discount = re.search(r'Discount\s+\-?\$?([\d,]+\.\d{2})', text, re.IGNORECASE)
    if discount:
        items.append(ChargeItem(charge_description='Discount', amount=-float(discount.group(1).replace(',', ''))))
    return items
