"""Waste Disposal LLC charge extraction."""
import re
from typing import List
from ..models import ChargeItem

def extract_waste_disposal(text: str) -> List[ChargeItem]:
    items = []
    item_pattern = re.compile(
        r'((?:Swap|Haul|Delivery|Dump|Final|Over\s*Tonnage|Rental|Disposal|Pick\s*Up|Exchange|Trip|Container|Service|Roll\s*Off|Removal|Live\s*Load)[\w\s\-()/#,.*]+?)\s+(\d+\.?\d*)\s+\$?([\d,]+\.?\d*)\s+\$?([\d,]+\.\d{2})',
        re.IGNORECASE
    )
    for m in item_pattern.finditer(text):
        desc = re.sub(r'\([\d/]+\)', '', m.group(1).strip()).strip()
        desc = re.sub(r'-WO0?#?\d+', '', desc).strip()
        desc = re.sub(r'\s+', ' ', desc)
        items.append(ChargeItem(
            charge_description=desc,
            amount=float(m.group(4).replace(',', '')),
            qty=float(m.group(2)) if float(m.group(2)) != 1.0 else None,
            unit_price=float(m.group(3).replace(',', '')),
            raw_text=m.group(0).strip()
        ))
    return items
