"""City Of Oxnard charge extraction."""
import re
from typing import List
from ..models import ChargeItem

def extract_city_of_oxnard(text: str) -> List[ChargeItem]:
    items = []
    service_pattern = re.compile(
        r'((?:CR|FL|RO|CT|BIN)\s+\d+\s*(?:YD|GAL|CY)\s+[\w\s]+?)\s+\$?([\d,]+\.\d{2})',
        re.IGNORECASE
    )
    for m in service_pattern.finditer(text):
        items.append(ChargeItem(charge_description=m.group(1).strip(), amount=float(m.group(2).replace(',', ''))))
    if not items:
        generic = re.compile(
            r'([\w\s\-/&]+?(?:SERVICE|CHARGE|FEE|COLLECTION|DISPOSAL|RENTAL|REFUSE|RECYCL|TRASH|WASTE)[\w\s]*?)\s+\$?([\d,]+\.\d{2})',
            re.IGNORECASE
        )
        for m in generic.finditer(text):
            desc = m.group(1).strip()
            amount = float(m.group(2).replace(',', ''))
            if amount > 0 and len(desc) > 3:
                items.append(ChargeItem(charge_description=desc, amount=amount))
    return items
