"""Master PAC Services charge extraction.

Format (repair narrative):
    Services  Quantity  Parts & Labor  Total
    e.g. "Customer Name ... 1 $810.00 $810.00"
    Parts listed in narrative: "Hinges= $60.00"
    Travel and labor: "Travel: $225.00", "Labor: 2 Techs x 3hrs= $450.00"
    Additional trips: "1st Trip 1 $300.00 $300.00"
"""

import re
from typing import List
from ..models import ChargeItem


def extract_master_pac(text: str) -> List[ChargeItem]:
    """Extract charge items from Master PAC Services invoice OCR text."""
    items = []

    # Main service line: "DESCRIPTION QTY $TOTAL $TOTAL"
    # e.g. "Customer Name ... 1 $810.00 $810.00"
    service_pattern = re.compile(
        r'((?:Service|Repair|Maintenance|Inspection|'
        r'Trip|Travel|Labor|Parts|Install)[\w\s\-/&,.]*?)\s+'
        r'(\d+)\s+'
        r'\$?([\d,]+\.?\d*)\s+'
        r'\$?([\d,]+\.\d{2})',
        re.IGNORECASE
    )

    for m in service_pattern.finditer(text):
        desc = m.group(1).strip()
        qty = int(m.group(2))
        rate = float(m.group(3).replace(',', ''))
        amount = float(m.group(4).replace(',', ''))

        # Skip total/due lines
        if any(w in desc.upper() for w in ['TOTAL', 'DUE', 'PAGE', 'AMOUNT']):
            continue

        if len(desc) > 3 and amount > 0:
            items.append(ChargeItem(
                charge_description=desc,
                amount=amount,
                qty=float(qty) if qty > 1 else None,
                unit_price=rate if rate != amount else None,
                raw_text=m.group(0).strip()
            ))

    # Individual cost items: "Travel: $225.00", "Labor: 2 Techs x 3hrs= $450.00"
    cost_pattern = re.compile(
        r'((?:Travel|Labor|Parts|Welding|Hinges|Materials?)[\w\s:×x]*?)'
        r'[=:]\s*\$?([\d,]+\.\d{2})',
        re.IGNORECASE
    )

    for m in cost_pattern.finditer(text):
        desc = m.group(1).strip().rstrip(':')
        amount = float(m.group(2).replace(',', ''))

        # Only add if not already in items as a broader line
        if not any(abs(i.amount - amount) < 0.01 for i in items if i.amount is not None):
            items.append(ChargeItem(
                charge_description=desc,
                amount=amount,
                raw_text=m.group(0).strip()
            ))

    return items
