"""PSI Waste Equipment Services charge extraction.

Format (parts + labor):
    Description  Price  Total
    e.g. "Travel Charge Service Area E. - [SA-37976] 1 575.00 575.00"
    e.g. "Work Description: ... 1.75 105.00 183.75"
    Parts list: "Hose 1/2 X 25\" 1 45.00 45.00"
    e.g. "Oil AW46 Gallons 15 20.00 300.00"
"""

import re
from typing import List
from ..models import ChargeItem


def extract_psi_waste(text: str) -> List[ChargeItem]:
    """Extract charge items from PSI Waste Equipment invoice OCR text."""
    items = []

    # Line items: "DESCRIPTION QTY RATE AMOUNT"
    # e.g. "Travel Charge Service Area E. - [SA-37976] 1 575.00 575.00"
    # e.g. "Hose 1/2 X 25\" 1 45.00 45.00"
    item_pattern = re.compile(
        r'([\w\s\-/&,.\[\]"\'()+:]+?)\s+'
        r'(\d+\.?\d*)\s+'                  # qty
        r'([\d,]+\.?\d*)\s+'               # rate
        r'([\d,]+\.\d{2})\s*$',            # amount
        re.MULTILINE
    )

    for m in item_pattern.finditer(text):
        desc = m.group(1).strip()
        qty = float(m.group(2))
        rate = float(m.group(3).replace(',', ''))
        amount = float(m.group(4).replace(',', ''))

        # Skip non-item lines
        skip = ['SUBTOTAL', 'SALES TAX', 'INVOICE AMOUNT', 'PAYMENTS',
                'BALANCE DUE', 'PAGE', 'DATE', 'DESCRIPTION']
        if any(w in desc.upper() for w in skip):
            continue

        # Skip zero-amount or very short descriptions
        if amount == 0 or len(desc) < 3:
            continue

        items.append(ChargeItem(
            charge_description=desc,
            amount=amount,
            qty=qty if qty != 1.0 else None,
            unit_price=rate,
            raw_text=m.group(0).strip()
        ))

    return items
