"""Atlantic Waste (Mid-Atlantic Waste) charge extraction.

Format (segment totals):
    SEGMENT : N  Description
    ITEM / LOT ID  DESCRIPTION  QTY  PRICE  CORE  TOTAL
    e.g. "FUEL SURCHARGE 1.00 25.00 25.00"
    e.g. "LABOR 300.00"
    Segment total: "PARTS 0.00 LABOR 300.00 MISC 25.00 TAX 0.00 TOTAL 325.00"
"""

import re
from typing import List
from ..models import ChargeItem


def extract_atlantic_waste(text: str) -> List[ChargeItem]:
    """Extract charge items from Atlantic Waste invoice OCR text."""
    items = []

    # Item line: "DESCRIPTION QTY PRICE TOTAL"
    item_pattern = re.compile(
        r'([\w\s\-/&,.]+?)\s+'
        r'(\d+\.?\d*)\s+'
        r'([\d,]+\.?\d*)\s+'
        r'([\d,]+\.\d{2})',
        re.IGNORECASE
    )

    # Focus on the items section (between ITEM header and SEGMENT TOTAL)
    items_section = re.search(
        r'(?:ITEM\s*/\s*LOT\s*ID|DESCRIPTION\s+QTY\s+PRICE)(.*?)(?:SEGMENT\s+\d+\s+TOTAL|Page)',
        text, re.DOTALL | re.IGNORECASE
    )

    search_text = items_section.group(1) if items_section else text

    for m in item_pattern.finditer(search_text):
        desc = m.group(1).strip()
        qty = float(m.group(2))
        rate = float(m.group(3).replace(',', ''))
        amount = float(m.group(4).replace(',', ''))

        # Skip summary lines
        if any(w in desc.upper() for w in ['SEGMENT', 'TOTAL', 'PAGE', 'PARTS', 'MISC', 'TAX']):
            continue

        if len(desc) > 2 and amount > 0:
            items.append(ChargeItem(
                charge_description=desc,
                amount=amount,
                qty=qty if qty != 1.0 else None,
                unit_price=rate,
                raw_text=m.group(0).strip()
            ))

    # Standalone LABOR line: "LABOR 300.00"
    labor_match = re.search(r'(LABOR)\s+([\d,]+\.\d{2})', text, re.IGNORECASE)
    if labor_match:
        amount = float(labor_match.group(2).replace(',', ''))
        if not any(i.charge_description.upper() == 'LABOR' for i in items):
            items.append(ChargeItem(
                charge_description='Labor',
                amount=amount,
                raw_text=labor_match.group(0).strip()
            ))

    return items
