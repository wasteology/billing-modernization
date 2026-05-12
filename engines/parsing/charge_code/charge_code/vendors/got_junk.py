"""1-800-GOT-JUNK charge extraction."""
import re
from typing import List
from ..models import ChargeItem

def extract_got_junk(text: str) -> List[ChargeItem]:
    items = []
    items_section = re.search(r'(?:Description\s+Quantity\s+Rate\s+Amount)\s*\n(.*?)(?:Subtotal|Tax|Total)', text, re.DOTALL | re.IGNORECASE)
    search_text = items_section.group(1) if items_section else text
    charge_pattern = re.compile(r'([\w\s\-/&,#.]+?)\s+(\d+)\s+\$?([\d,]+\.?\d*)\s+\$?([\d,]+\.\d{2})', re.IGNORECASE)
    for m in charge_pattern.finditer(search_text):
        desc = m.group(1).strip()
        if any(w in desc.upper() for w in ['SUBTOTAL', 'TAX', 'TOTAL', 'CURRENCY', 'DISCOUNT', 'INVOICE', 'EFT', 'BANKING']):
            continue
        if len(desc) > 3:
            items.append(ChargeItem(
                charge_description=desc,
                amount=float(m.group(4).replace(',', '')),
                qty=float(m.group(2)) if int(m.group(2)) > 1 else None,
                unit_price=float(m.group(3).replace(',', '')),
                raw_text=m.group(0).strip()
            ))
    discount = re.search(r'Discount\s+\$?([\d,]+\.\d{2})', text, re.IGNORECASE)
    if discount:
        items.append(ChargeItem(charge_description='Discount', amount=-float(discount.group(1).replace(',', ''))))
    return items
